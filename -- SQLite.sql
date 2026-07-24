-- SQLite
select * from prices where fund_id = "YF:BTEC.L";

select * from instruments;


UPDATE instruments 
SET category = 'Defence'
WHERE category IN ('Europe Defence', 'World Defence');

SELECT fund_id, name, category, asset_type 
FROM instruments 
WHERE asset_type = 'Infrastructure';

SELECT * FROM snapshot_categories 
WHERE category IN ('Europe Defence', 'World Defence')
LIMIT 5;

UPDATE snapshot_categories 
SET category = 'Defence'
WHERE category IN ('Europe Defence', 'World Defence');