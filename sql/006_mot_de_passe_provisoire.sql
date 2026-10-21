-- ============================================================
-- Frip'Lux : script 006 (mots de passe)
-- 1. doit_changer_mot_de_passe : vrai quand le mot de passe a été donné par l'administrateur
-- (création du compte ou mot de passe provisoire) ; l'utilisateur doit alors choisir
-- son propre mot de passe à la connexion suivante.
--
-- Ne supprime aucune donnée. Peut être relancé sans risque.
-- À appliquer avec : python manage.py appliquer_sql sql/006_mot_de_passe_provisoire.sql
-- ============================================================

ALTER TABLE users ADD COLUMN IF NOT EXISTS doit_changer_mot_de_passe boolean NOT NULL DEFAULT false;

-- Droits par personne dans l'administration (Django) : tables attendues par le modèle des utilisateurs.
-- Sans elles, un compte « Statut équipe » qui n'est pas super-administrateur provoque une erreur dans l'admin.
CREATE TABLE IF NOT EXISTS users_groups (
    id       bigserial PRIMARY KEY,
    user_id  bigint  NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    group_id integer NOT NULL REFERENCES auth_group(id) ON DELETE CASCADE,
    CONSTRAINT uq_users_groups UNIQUE (user_id, group_id)
);
CREATE TABLE IF NOT EXISTS users_user_permissions (
    id            bigserial PRIMARY KEY,
    user_id       bigint  NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission_id integer NOT NULL REFERENCES auth_permission(id) ON DELETE CASCADE,
    CONSTRAINT uq_users_user_permissions UNIQUE (user_id, permission_id)
);
