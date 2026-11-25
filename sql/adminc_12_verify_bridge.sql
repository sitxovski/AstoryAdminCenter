-- Copyright (c) 2026 @sitxovski (Discord)
/* adminc_12_verify_bridge.sql — проверка прав asda_bridge (мост P127, 18.11.2026). Запуск ПОД ЛОГИНОМ asda_bridge (deploy делает сам).
   Ожидание: только процедуры узла; ни таблиц моста, ни постановки команд, ни игровых баз, ни журнала панели. */
SET NOCOUNT ON;
SELECT 'adm.BridgeClaim EXEC'        AS chk, HAS_PERMS_BY_NAME('adm.BridgeClaim','OBJECT','EXECUTE')        AS v, 1 AS want
UNION ALL SELECT 'adm.BridgeResult EXEC',      HAS_PERMS_BY_NAME('adm.BridgeResult','OBJECT','EXECUTE'),      1
UNION ALL SELECT 'adm.BridgeHeartbeat EXEC',   HAS_PERMS_BY_NAME('adm.BridgeHeartbeat','OBJECT','EXECUTE'),   1
UNION ALL SELECT 'adm.BridgeNodeStart EXEC',   HAS_PERMS_BY_NAME('adm.BridgeNodeStart','OBJECT','EXECUTE'),   1
UNION ALL SELECT 'adm.BridgePresenceSet EXEC', HAS_PERMS_BY_NAME('adm.BridgePresenceSet','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.BridgePresenceDel EXEC', HAS_PERMS_BY_NAME('adm.BridgePresenceDel','OBJECT','EXECUTE'), 1
UNION ALL SELECT 'adm.BridgeEnqueue EXEC',     HAS_PERMS_BY_NAME('adm.BridgeEnqueue','OBJECT','EXECUTE'),     0
UNION ALL SELECT 'adm.bridge_cmd SELECT',      HAS_PERMS_BY_NAME('adm.bridge_cmd','OBJECT','SELECT'),         0
UNION ALL SELECT 'adm.bridge_cmd UPDATE',      HAS_PERMS_BY_NAME('adm.bridge_cmd','OBJECT','UPDATE'),         0
UNION ALL SELECT 'adm.bridge_presence DELETE', HAS_PERMS_BY_NAME('adm.bridge_presence','OBJECT','DELETE'),    0
UNION ALL SELECT 'adm.bridge_node UPDATE',     HAS_PERMS_BY_NAME('adm.bridge_node','OBJECT','UPDATE'),        0
UNION ALL SELECT 'adm.audit SELECT',           HAS_PERMS_BY_NAME('adm.audit','OBJECT','SELECT'),              0
UNION ALL SELECT 'adm.users SELECT',           HAS_PERMS_BY_NAME('adm.users','OBJECT','SELECT'),              0
UNION ALL SELECT 'Joy1 CONNECT',               ISNULL(HAS_PERMS_BY_NAME('Joy1',NULL,'CONNECT'), 0),           0
UNION ALL SELECT 'sysadmin',                   IS_SRVROLEMEMBER('sysadmin'),                                  0;
