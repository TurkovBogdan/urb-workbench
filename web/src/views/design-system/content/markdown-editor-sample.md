Stage 4 — reworking HOW the license gets its values. Before making changes, this records how
everything works as of 2026-09-17: checked against the code, addresses given. Open questions and
blockers live separately — `NOTE@271f8e548f`; the journal of what's been done — `NOTE@a3d1815018`.

## The scheme in two halves

The purchase is split across time: first CHECKOUT (the client clicked, the order is recorded,
money hasn't arrived yet), then FULFILLMENT (money arrived, the license changed). Weeks can pass
between them — an invoice lives for 30 days.

```
CHECKOUT
  storefront         GET  /spa/projects/{code}/tariffs
                     └─ TariffResolver::forLicense()  → [TariffOffer, …]
  click              POST /spa/projects/{code}/orders  {tariff, expected_price, expected_limits}
                     └─ CreateOrderRequest::intent()  → PurchaseIntent (a snapshot of what the client saw)
                        └─ OrderCheckout::create()
                           ├─ TariffResolver::forTariff()      — what's being sold NOW
                           ├─ mismatches(offer, intent)        — mismatch → 409, no order
                           ├─ resume()/sells()                 — live draft of the same intent
                           ├─ store()                          — order row + license_before snapshot
                           └─ handToPaySystem()                — txn_… transaction at Paddle

FULFILLMENT
  webhook/parsing    OrderService::…  or BillingIncidents (human decision on an incident)
                     └─ OrderCompletion::complete()
                        └─ applyToLicense()
                           └─ LicenseManager::applyPurchase()
                              ├─ takeMoney(): LicenseSubscribe | LicenseUpgrade | LicenseRenew
                              │   └─ LicenseAction::applyLicenseChanges($tariff->limits($overrides))
                              │      → writes the licenses.limit_* columns + limits_version + a journal row
                              └─ LicenseKeyManager::syncKeys() — top up keys to limit_instances
```

⚠️ The key fact of the whole scheme: **the values in the license come from the CATALOG at the
moment of payment, not from the order snapshot**. The snapshot hands over exactly one value — the instance count.

## Today's tariff catalog

`Modules/License/app/Enums/LicenseTariff.php` — a closed enum of five cases and the single source
of values; the docblock states exactly that.

| Tariff | users | runners | instances | nodes | resources | rank |
|---|---|---|---|---|---|---|
| `community` | null | null | null | null | null | 0 |
| `pro1` | 1 | 1 | 1 | null | null | 10 |
| `pro4` | 4 | 4 | 1 | null | null | 20 |
| `pro10` | 10 | 10 | 1 | null | null | 30 |
| `enterprise_core` | 1 000 000 | 1 000 000 | 1 | null | null | 40 |

- `limits(array $overrides)` (`:124-144`) assembles exactly five keys under the column names
  `licenses.limit_*` and throws `UnknownLicenseLimitException` on an unknown key. ALL issuances
  go through it: purchase, upgrade, plan change, trial start, checkout, storefront, admin catalog, stand.
- `nodesLimit()` and `resourcesLimit()` always return `null` — the catalog does not assign
  infrastructure. `instancesLimit()` = 1 for any paid tier. `UNLIMITED = 1 000 000` — how
  "unlimited" is expressed when a number has to be named.
- Precedence is one-dimensional: `rank()` + `isAbove()`, `ranked()` also sets the storefront order.

**The price does NOT live here.** `LicenseTariffPrice::forTariff()` matches the case against a config
row `billing.tariffs.pro{1,4,10}` (`BILLING_TARIFF_PRO*_PRICE`, `_PRICE_ID`, `_PRODUCT_ID`);
`community` and `enterprise_core` have no price at all — `null`. The Paddle amount is authoritative,
our copy exists so the catalog can be read without a network call.

**The offer** is assembled by `TariffResolver::makeOffer()` (`:62-94`) and returns a `TariffOffer` —
currency, price, list price, `pri_…`/`pro_…`, purchase type, term and a preview of the new expiry
date. The purchase type is decided by `purchaseTypeFor()` (`:142-179`) along two axes — the
license's commercial stage and the tariff relationship: not purchased → `subscription`; same tariff
→ `renewal`; not above the current one → `null` (no button); expired, or the remaining period is
shorter than `billing.upgrade.min_days` → `subscription`; otherwise `upgrade`. The upgrade surcharge is computed by `UpgradeChargeResolver::for()` — the difference in catalog prices for the unused
remainder of the year, rounded up to a whole dollar.

## Checkout: what gets written to the order

`CreateOrderRequest` is the single place that translates wire names (`users`, `runners`, `instances`,
`nodes`, `resources`) into columns (`limit_*`); `PurchaseIntent` is a snapshot of what the client
saw, and it decides NOTHING.

`OrderCheckout::mismatches()` (`:525-557`) checks four things: purchase type, price, currency and
**`$offer->purchaseTariff->limits() !== $intent->limits`** — a strict comparison of the whole
arrays. A mismatch — `OfferMismatchException` and 409, no order. ⚠️ Hence the rule from earlier
stages: the set of keys changes in ONE pass across the whole chain.

`store()` (`:567-609`) writes the order row; the values are taken from the TARIFF, not from the offer and not from the intent:

| Order column | Source |
|---|---|
| `license_type`, `license_tariff` | `$tariff->type()`, `$tariff->value` |
| `license_users`, `license_runners`, `license_instances`, `license_nodes`, `license_resources` | `$tariff->*Limit()` one by one |
| `limits_version` | `Order::LIMITS_VERSION` (2.0) |
| `license_term_months` | `$offer->termMonths` (12, or `null` for an upgrade) |
| `amount`, `currency` | `$offer->price`, `$offer->currency` |
| `purchase_stage`, `created_by`, `license_before` | set outside `$fillable` |

`license_before` is a snapshot of the license BEFORE the purchase (`licenseSnapshot()`, `:614-628`):
type, tariff, status, all five values and the term. This is an AUDIT trail, the logic never reads it.

`resume()`/`sells()` (`:99-170`) return a live draft of the same person under the same intent.
`sells()` checks purchase type, tariff, amount, currency and the five values against the catalog;
it does not check the epoch — hence the open question about a draft from a previous epoch.

## Fulfillment: what gets applied to the license

`OrderCompletion::complete()` — two doors: the regular event delivery (`OrderService`) and a human
decision on an incident (`BillingIncidents`). Guards: a missing license, an open incident,
`processed_at` under a row lock.

`applyToLicense()` (`:115-127`) — the heart of the stage:

```php
$this->licenses->applyPurchase(
    $license,
    LicenseTariff::from($order->license_tariff),
    $order->license_instances,     // ← the only value coming from the snapshot
    $order->license_term_months,
    $order->purchase_type === PurchaseType::Renewal,
    $order->creator,
);
```

`LicenseManager::applyPurchase()` turns this into `$limits = ['limit_instances' => $instances]`
(`:73`) and calls `takeMoney()`, where there are three doors:

| Condition | Action | What it does with the values |
|---|---|---|
| `termMonths === null` | `LicenseUpgrade` | `$tariff->limits($limits)` — OVERWRITE from the catalog |
| `renewal === true` | `LicenseRenew` | doesn't touch the values at all (the rule is stated in the code) |
| otherwise | `LicenseSubscribe` | `$tariff->limits($limits)` — OVERWRITE from the catalog |

Then a shared bottom layer: `LicenseAction::applyLicenseChanges()` writes the columns, appends
`limits_version = 2.0` (the rule from stage 2) and puts the diff in the journal;
`LicenseKeyManager::syncKeys()` tops keys up to `limit_instances`, it doesn't trim a surplus.

⚠️ This is where all the stage's pain comes from: **purchased nodes, resources, seats and runners
never reach the license** — only the tariff and the instance count do. As long as the catalog is
the configuration, this goes unnoticed; with a per-value tariff it's a silent loss of the purchase.

Nearby, the same values are written by `LicenseChangePlan` (admin plan change,
`ChangeLicensePlanRequest::LIMITS`, five keys) and `TrialStart` (trial issuance) — both through the
same `limits($overrides)`.

## Where the values live

| Layer | Names | Who writes |
|---|---|---|
| License | `licenses.limit_users/runners/instances/nodes/resources` + `limits_version` | only actions in `Modules/License/app/Actions/**` |
| Order | `billing_orders.license_*` + `limits_version` + `license_before` | `OrderCheckout::store()`, demo — `InvoiceLedger` |
| Wire | `users`, `runners`, `instances`, `nodes`, `resources` | read resources and `CreateOrderRequest` |
| Engine token | claim `users`, `nodes`, `resources`, `runners`, `uis` | `SubscriptionLicenseToken` |

## What we'll change and why

**1. The catalog stops being the source of configuration.** `LicenseTariff` remains the reference
for tiers (community / pro / enterprise) and for what genuinely depends on the tier, but the five
values for pro must come from the client's CHOICE, not from the enum case. Hence: infrastructure
tiers and surcharges move into config, and `nodesLimit()`/`resourcesLimit()`/`instancesLimit()`
stop being constants of the case.

**2. The offer learns to carry a configuration and its price.** `TariffOffer` today is addressed
by case (`purchaseTariff`), and the price is taken from `LicenseTariffPrice` for that case. What's
needed is either a tier as a separate axis of the offer, or a `custom` case with a price computed
by a calculator. This touches `TariffResolver::makeOffer()`, `LicenseTariffPrice`, `TariffOfferResource` and the storefront.

**3. Comparing configurations instead of `rank()`.** `purchaseTypeFor()` distinguishes renewal from
upgrade via case equality and `isAbove()`. Five values can't be compared as a single number: we
need a predicate "does the new configuration cover the old one" and a rule for the mixed case (more
nodes, fewer seats). The same `rank()` still holds the downgrade ban and the storefront order.

**4. Storefront reconciliation goes by configuration.** `mismatches()` compares
`$offer->purchaseTariff->limits()` against the intent — that is, catalog against catalog. It will
have to compare the offer's configuration against the intent's configuration; keep the strict array
comparison — it catches a mismatch between the storefront and the server.

**5. The order writes what was actually bought.** `store()` takes values from the tariff one by one
— replace this with the offer's/configuration's values. The columns for this already exist, no schema change is needed.

**6. Payment applies the SNAPSHOT, not the catalog.** `applyToLicense()` passes a single value — it
must pass all five; `LicenseManager::applyPurchase()` accepts `?int $instances` — it must accept an
array of values and put it into `$tariff->limits($overrides)` whole. This also closes two known
defects: a purchase overwriting contractual instances
(`work/audit/problems/2026-09-04-purchase-resets-contract-instances.md`) and nodes and resources
being wiped on an admin plan change.

**7. Renewal stays without values.** `LicenseRenew` deliberately doesn't touch them; under a
per-value model this rule needs to be confirmed EXPLICITLY — otherwise a renewal will freeze the
old configuration while the client thinks they bought a new one.

**8. Keys follow instances.** `syncKeys()` mints keys up to `limit_instances`; with three instances
on Pro this will work on its own, but it needs checking — today a paid tier always has exactly one.

**9. Forms and the storefront.** `AdminLicenseEditor::REQUIRED_LIMIT_KEYS` holds three of the five
values precisely because the catalog stays silent on nodes and resources: once price depends on the
values, the list has to become complete. The client-facing Plan screen shows three values and a
fixed list of tariffs — that's where the calculator appears.

## What the stage does NOT touch

The token and its claims (the contract shape with the engine is already in place), the license
journal and its axes, the limits epoch (the rule from stage 2 works as is), Paddle subscriptions and
recurring payments, engine-side enforcement — the `resources` claim is still not read by `pro_impl`.

## Traps already paid for

- **Strict array comparison of limits** in `mismatches()` and `sells()`: a different SET of keys =
  409 on every purchase. Change the set only in one pass across the whole chain.
- **Exactly one place computes the price** — the catalog; checkout does not recompute it. A second
  computation would drift from the storefront; this is a legacy ailment, named in the `OrderCheckout` docblock.
- **An in-flight order survives a deploy** only because the values are taken from the catalog at the
  moment of payment. As soon as the snapshot becomes the source — an order placed before the model
  change will start applying ITS OWN set of values; that's exactly why the order has `limits_version`.
- **`applyPurchase()` holds the rule "no upgrading from a trial"** and throws
  `TrialAlreadyRunningException` — it must not be lost when the signature is reworked.
