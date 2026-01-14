# Keyword Aliases Setup Guide

This guide explains how to set up the keyword aliases system in Supabase.

## Overview

The keyword aliases system allows users to map alternative terms (translations, synonyms) to keywords. When a user searches for an alias, the system will find results for the associated keyword.

Example:
- Keyword: "tank"
- Aliases: "xe tăng" (Vietnamese), "armor"

When a user searches for "xe tăng", the system will return results for "tank".

## Setup Steps

### 1. Run SQL Migration

Execute the SQL migration file in your Supabase SQL Editor:

```bash
# File: deploy/setup_keyword_aliases.sql
```

Or copy and paste the contents of `deploy/setup_keyword_aliases.sql` into the Supabase SQL Editor and run it.

This will create:
- `keyword_aliases` table
- Indexes for fast lookups
- Trigger for automatic `updated_at` timestamp

### 2. Migrate Existing Aliases (Optional)

If you have existing aliases in `data/alias_dictionary.json`, migrate them to Supabase:

```bash
python scripts/migrate_aliases_to_supabase.py
```

This script will:
- Read aliases from the JSON file
- Insert them into Supabase
- Create a backup of the original file

### 3. Verify Setup

Test that the table was created:

```sql
SELECT * FROM keyword_aliases LIMIT 5;
```

## API Endpoints

The following endpoints are available:

### GET `/api/manage/aliases`
Get all aliases grouped by keyword.

**Response:**
```json
{
  "keywords": [
    {
      "id": "keyword-...",
      "name": "tank",
      "language": "EN",
      "aliases": [
        {"id": "...", "name": "xe tăng", "createdAt": "..."}
      ],
      "createdAt": "..."
    }
  ],
  "lastUpdated": "..."
}
```

### POST `/api/manage/aliases`
Add a new alias.

**Request:**
```json
{
  "keyword": "tank",
  "alias": "xe tăng",
  "language": "en"
}
```

### DELETE `/api/manage/aliases`
Delete an alias.

**Request:**
```json
{
  "keyword": "tank",
  "alias": "xe tăng"
}
```

### POST `/api/manage/aliases/save`
Bulk save aliases (used by frontend).

## Database Schema

```sql
CREATE TABLE keyword_aliases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    keyword TEXT NOT NULL,                    -- Main keyword
    alias TEXT NOT NULL,                      -- Alias term
    language TEXT DEFAULT 'en',                -- 'en' or 'vi'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(keyword, alias)
);
```

## Usage in Code

### Add an alias:
```python
from backend.storage.keyword_storage import insert_alias

insert_alias("tank", "xe tăng", "vi")
```

### Get aliases for a keyword:
```python
from backend.storage.keyword_storage import get_aliases_for_keyword

aliases = get_aliases_for_keyword("tank")
# Returns: ["xe tăng", "armor"]
```

### Find keyword by alias:
```python
from backend.storage.keyword_storage import find_keyword_by_alias

keywords = find_keyword_by_alias("xe tăng")
# Returns: [{"keyword": "tank", "alias": "xe tăng", "language": "vi"}]
```

## Notes

- Aliases are case-insensitive for lookups
- The system supports bidirectional lookups (keyword ↔ alias)
- Language codes can be 'en'/'EN' or 'vi'/'VN' (normalized to lowercase in DB)
- Duplicate keyword-alias pairs are prevented by UNIQUE constraint

