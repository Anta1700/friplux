-- ============================================================
-- Frip'Lux : script 001 (à lancer UNE fois avec le compte postgres)
-- Donne la propriété des tables Frip'Lux au compte de l'application
-- friplux_user, pour qu'il puisse appliquer les scripts suivants.
-- Ne modifie aucune donnée.
-- ============================================================
GRANT USAGE, CREATE ON SCHEMA public TO friplux_user;

DO $$
DECLARE
    t record;
BEGIN
    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
        -- Les séquences des identifiants (bigserial) suivent automatiquement leur table.
        EXECUTE format('ALTER TABLE public.%I OWNER TO friplux_user', t.tablename);
    END LOOP;
END $$;
