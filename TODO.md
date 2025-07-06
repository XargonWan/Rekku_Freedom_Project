# BUGS:

## No memories found
Use SQLite + FTS5

```
🧞‍♀️ Rekku è online.
[DEBUG] context_memory[-1002654768042] = [{'message_id': 187, 'username': 'Jay Cheshire', 'usertag': '@Xargon', 'text': '@Rekku_the_bot sono jay', 'timestamp': '2025-06-23T06:45:50+00:00'}]
[DEBUG] Messaggio da 31321637 (supergroup): @Rekku_the_bot sono jay
[DEBUG/manual] Messaggio ricevuto in modalit� manuale da chat_id=-1002654768042
[DEBUG/manual] Context attivo, invio cronologia
[DEBUG] Query robusta:

        SELECT DISTINCT content
        FROM memories
        WHERE json_valid(tags)
          AND EXISTS (
              SELECT 1
              FROM json_each(memories.tags)
              WHERE json_each.value IN (?)
          )
     ORDER BY timestamp DESC LIMIT ?
[DEBUG] Parametri: ['jay', 5]
[DEBUG/manual] Messaggio inoltrato e tracciato
```

# TODO
- creare una tabella separate per gli utenti, storare li la bio degli utenti assegnandogli uno userid, sennò gli utenti diventano troppe memorie sparse
- fixare la ricerca delle memorie che non funziona (sqlite + fts5)
- riscrivere i prompt fatti bene allegando anche il prompt base
- scrivere il plugin Selenium
- interfaccia userbot
- Refine the actual logic to be an handler for Telgram
- Create a handler for Discord
- Create a hanlder for ReVolt
- Actually train her on RetroDECK Wiki
