-- ============================================================
-- Frip'Lux : script 006 (mots de passe)
-- doit_changer_mot_de_passe : vrai quand le mot de passe a été donné par l'administrateur
-- (création du compte ou mot de passe provisoire) ; l'utilisateur doit alors choisir
-- son propre mot de passe à la connexion suivante.
--
-- Ne supprime aucune donnée. Peut être relancé sans risque.
-- À appliquer avec : python manage.py appliquer_sql sql/006_mot_de_passe_provisoire.sql
-- ============================================================

ALTER TABLE users ADD COLUMN IF NOT EXISTS doit_changer_mot_de_passe boolean NOT NULL DEFAULT false;
