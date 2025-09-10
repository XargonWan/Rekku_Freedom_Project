#!/usr/bin/env python3
"""
Test script per verificare l'integrazione del bio_manager
"""

import asyncio
import sys
import os

# Aggiungi il path del progetto
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_bio_manager():
    """Test basic bio_manager functionality"""
    try:
        # Import del plugin
        from plugins.bio_manager import (
            init_bio_table,
            get_bio_light, 
            get_bio_full,
            update_bio_fields,
            append_to_bio_list,
            add_past_event,
            alter_feeling
        )
        
        print("✅ Import del bio_manager riuscito!")
        
        # Test della connessione database
        print("🔧 Testando connessione database...")
        await init_bio_table()
        print("✅ Inizializzazione tabella bio completata!")
        
        # Test delle funzioni principali
        print("🔧 Testando funzioni bio...")
        
        test_user_id = "test_user_123"
        
        # Test update_bio_fields
        await update_bio_fields(test_user_id, {
            "known_as": ["TestUser", "TU"],
            "likes": ["python", "coding"],
            "information": "Test user for bio_manager"
        })
        print("✅ update_bio_fields funziona!")
        
        # Test get_bio_light
        light_bio = await get_bio_light(test_user_id)
        print(f"✅ get_bio_light: {light_bio}")
        
        # Test get_bio_full
        full_bio = await get_bio_full(test_user_id)
        print(f"✅ get_bio_full: user_id={full_bio.get('id')}")
        
        # Test append_to_bio_list
        await append_to_bio_list(test_user_id, "likes", "testing")
        print("✅ append_to_bio_list funziona!")
        
        # Test add_past_event
        await add_past_event(test_user_id, "Test event")
        print("✅ add_past_event funziona!")
        
        # Test alter_feeling
        await alter_feeling(test_user_id, "happy", 8)
        print("✅ alter_feeling funziona!")
        
        print("\n🎉 Tutti i test sono passati! Il bio_manager è integrato correttamente.")
        
    except Exception as e:
        print(f"❌ Errore durante il test: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    print("🧪 Test integrazione bio_manager\n")
    
    # Esegui i test
    result = asyncio.run(test_bio_manager())
    
    if result:
        print("\n✅ Test completato con successo!")
        sys.exit(0)
    else:
        print("\n❌ Test fallito!")
        sys.exit(1)
