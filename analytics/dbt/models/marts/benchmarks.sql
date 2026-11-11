-- 12-month reference per tenant and product (spec 3.3.1 item 3). The sanity engine decides what to do with a
-- small `n`; this mart only reports it. `as_of` is the newest price seen, not the wall clock.
select
    tenant_id,
    product_key,
    count() as n,
    quantileExact(0.25)(landed_unit_cost_eur_minor) as p25_eur_minor,
    quantileExact(0.5)(landed_unit_cost_eur_minor) as median_eur_minor,
    quantileExact(0.75)(landed_unit_cost_eur_minor) as p75_eur_minor,
    max(date) as as_of
from {{ source('apex_pg', 'price_history') }}
where date > (select max(date) from {{ source('apex_pg', 'price_history') }}) - 365
group by tenant_id, product_key
