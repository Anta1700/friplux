-- ============================================================
-- Frip'Lux : script 010
-- Traduction française du libellé fournisseur (ex. « GIUBBOTTI BAMBINO » -> « Blousons enfant »).
-- Le libellé d'origine reste tel quel ; la traduction est imprimée en dessous sur l'étiquette.
--
-- Ne supprime aucune donnée. Peut être relancé sans risque.
-- À appliquer avec : python manage.py appliquer_sql sql/010_traduction_references.sql
-- ============================================================

ALTER TABLE references_fournisseurs ADD COLUMN IF NOT EXISTS libelle_traduit varchar(200);
