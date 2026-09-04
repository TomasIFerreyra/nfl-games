-- Enable pg_trgm extension for fuzzy trigram text search and GIN indexes
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Enable pgcrypto / uuid-ossp for UUID generation functions if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;
