-- ============================================================
-- Frip'Lux : script 008
-- Lien public secret de chaque facture : le client scanne le QR code de la facture
-- (écran, PDF ou papier) et retrouve SA facture sur son téléphone, sans compte.
--
-- - factures.jeton_public       : partie secrète du lien (impossible à deviner, unique)
-- - factures.lien_public_actif  : un administrateur peut désactiver le lien d'une facture
-- Les jetons des factures existantes sont créés automatiquement par l'application.
--
-- Ne supprime aucune donnée. Peut être relancé sans risque.
-- À appliquer avec : python manage.py appliquer_sql sql/008_facture_lien_public.sql
-- ============================================================

ALTER TABLE factures ADD COLUMN IF NOT EXISTS jeton_public      varchar(64);
ALTER TABLE factures ADD COLUMN IF NOT EXISTS lien_public_actif boolean NOT NULL DEFAULT true;
CREATE UNIQUE INDEX IF NOT EXISTS uq_factures_jeton_public ON factures (jeton_public) WHERE jeton_public IS NOT NULL;
