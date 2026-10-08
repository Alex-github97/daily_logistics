-- Inicialización de la base de datos Daily Logistics
-- Este script se ejecuta una sola vez al crear el contenedor PostgreSQL

-- Extensiones útiles
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Índices adicionales de rendimiento para búsqueda de texto
-- Se crean después de que SQLAlchemy crea las tablas
-- Los índices principales son manejados por los modelos

-- Configuración de timezone
SET timezone = 'America/Bogota';

COMMENT ON DATABASE daily_logistics IS 'Daily Logistics - WMS, POS y TMS multicliente';
