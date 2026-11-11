-- Landed unit cost per tenant, product and day (EUR minor units). Source of the benchmark below.
select
    tenant_id,
    product_key,
    date,
    count() as n,
    min(landed_unit_cost_eur_minor) as min_eur_minor,
    quantileExact(0.5)(landed_unit_cost_eur_minor) as median_eur_minor,
    max(landed_unit_cost_eur_minor) as max_eur_minor
from {{ source('apex_pg', 'price_history') }}
group by tenant_id, product_key, date
