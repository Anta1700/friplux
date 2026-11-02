-- ============================================================
-- Frip'Lux : script 011
-- Poids du lot facultatif : certaines fiches fournisseur ne donnent pas le poids
-- (ex. chaussures et sacs de la fiche Hiver MITUMBATEX). On ne l'invente pas.
-- La contrainte « poids > 0 » reste valable quand le poids est renseigné.
--
-- Ne supprime aucune donnée. Peut être relancé sans risque.
-- À appliquer avec : python manage.py appliquer_sql sql/011_poids_lot_facultatif.sql
-- ============================================================

ALTER TABLE lots ALTER COLUMN poids_kg DROP NOT NULL;
