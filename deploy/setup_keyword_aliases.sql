-- Create keyword_aliases table in Supabase
-- This table stores keyword-alias mappings for the Keyword Finder feature

CREATE TABLE IF NOT EXISTS keyword_aliases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    keyword TEXT NOT NULL,                    -- Main keyword (e.g., "tank")
    alias TEXT NOT NULL,                      -- Alias (e.g., "xe tăng", "armor")
    language TEXT DEFAULT 'en',                -- 'en' or 'vi' (or 'EN'/'VN' to match existing format)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(keyword, alias)                    -- Prevent duplicate entries
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS keyword_aliases_keyword_idx ON keyword_aliases(keyword);
CREATE INDEX IF NOT EXISTS keyword_aliases_alias_idx ON keyword_aliases(alias);
CREATE INDEX IF NOT EXISTS keyword_aliases_language_idx ON keyword_aliases(language);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_keyword_aliases_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to automatically update updated_at
CREATE TRIGGER update_keyword_aliases_updated_at
BEFORE UPDATE ON keyword_aliases
FOR EACH ROW
EXECUTE FUNCTION update_keyword_aliases_updated_at();

-- Add comments for documentation
COMMENT ON TABLE keyword_aliases IS 'Stores keyword-alias mappings for search expansion in Keyword Finder';
COMMENT ON COLUMN keyword_aliases.keyword IS 'The primary keyword that appears in documents';
COMMENT ON COLUMN keyword_aliases.alias IS 'Alternative term that maps to the keyword (e.g., translation or synonym)';
COMMENT ON COLUMN keyword_aliases.language IS 'Language code: en/EN for English, vi/VN for Vietnamese';

