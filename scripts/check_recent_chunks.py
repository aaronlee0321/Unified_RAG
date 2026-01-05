"""Quick check of recent chunks."""
import sys
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

load_dotenv(project_root / '.env')

from backend.storage.supabase_client import get_supabase_client

client = get_supabase_client(use_service_key=True)
result = client.table('gdd_chunks').select('chunk_id, doc_id').eq('doc_id', 'Combat_Module_Tank_War_Mobile_Skill_Control_System').limit(5).execute()

print('Chunks for Combat_Module_Tank_War_Mobile_Skill_Control_System:')
for c in (result.data or []):
    print(f'  chunk_id: {c["chunk_id"]}')


