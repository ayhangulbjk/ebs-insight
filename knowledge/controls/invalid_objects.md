# Invalid Objects - Oracle EBS R12 Domain Knowledge

## Overview
Invalid objects are database objects (procedures, packages, views, materialized views, triggers, etc.) that failed to compile successfully. They are marked as INVALID in DBA_OBJECTS and cannot be executed until recompiled.

## Why They Occur
Common causes in EBS R12 environments:
1. **Missing dependencies** - Referenced objects dropped or invalidated
2. **Grant/privilege issues** - Missing execute/select grants on dependencies
3. **Synonym problems** - Missing or broken synonyms pointing to invalid targets
4. **Patch application** - Patches may temporarily invalidate dependent objects
5. **ADOP cycles** - Edition-based redefinition can cause temporary invalidations
6. **Schema changes** - ALTER TABLE, DROP COLUMN, etc. invalidate dependent objects

## Severity Guidelines
- **0-10 objects**: OK - Normal post-patch state
- **11-50 objects**: WARN - Investigate before next patching cycle
- **51-100 objects**: WARN - Requires attention, may impact functionality
- **100+ objects**: CRIT - Immediate investigation required, functional impact likely
- **500+ objects**: CRITICAL - Major issue, system functionality severely impacted

## Recommended Checks & Actions

### Step 1: Identify Error Details
```sql
-- Get compilation errors for invalid objects
SELECT owner, name, type, line, position, text
FROM DBA_ERRORS
WHERE owner IN ('APPS', 'XXCUST')  -- Adjust for your custom schema
ORDER BY owner, name, line;

-- Alternative: ALL_ERRORS for non-DBA users
SELECT name, type, line, position, text
FROM ALL_ERRORS
WHERE owner = 'APPS'
ORDER BY name, line;
```

### Step 2: Check Dependency Chain
```sql
-- Find what each invalid object depends on
SELECT d.owner, d.name, d.type,
       d.referenced_owner, d.referenced_name, d.referenced_type
FROM DBA_DEPENDENCIES d
JOIN DBA_OBJECTS o ON d.owner = o.owner AND d.name = o.name AND d.type = o.type
WHERE o.status = 'INVALID'
  AND d.owner IN ('APPS', 'XXCUST')
ORDER BY d.owner, d.name;
```

### Step 3: Recompile Invalid Objects

**Method A: UTL_RECOMP (Recommended for bulk)**
```sql
-- Compile all invalid objects in APPS schema (runs in parallel)
EXEC UTL_RECOMP.RECOMP_SERIAL('APPS');

-- Or parallel compilation (faster, requires more resources)
EXEC UTL_RECOMP.RECOMP_PARALLEL(4, 'APPS');  -- 4 parallel threads
```

**Method B: Manual compilation (for specific objects)**
```sql
-- Procedures/Functions
ALTER PROCEDURE apps.procedure_name COMPILE;
ALTER FUNCTION apps.function_name COMPILE;

-- Packages (compile spec first, then body)
ALTER PACKAGE apps.package_name COMPILE SPECIFICATION;
ALTER PACKAGE apps.package_name COMPILE BODY;

-- Views
ALTER VIEW apps.view_name COMPILE;

-- Materialized Views
ALTER MATERIALIZED VIEW apps.mv_name COMPILE;

-- Triggers
ALTER TRIGGER apps.trigger_name COMPILE;
```

**Method C: EBS-specific compilation script**
```bash
# Run from application tier as applmgr user
cd $ADMIN_SCRIPTS_HOME
sqlplus apps/password @adutlrcmp.sql
```

### Step 4: Verify Resolution
```sql
-- Recheck invalid count after compilation
SELECT COUNT(*) as invalid_count
FROM DBA_OBJECTS
WHERE status = 'INVALID'
  AND owner IN ('APPS', 'XXCUST');

-- List remaining invalid objects by type
SELECT owner, object_type, COUNT(*) as count
FROM DBA_OBJECTS
WHERE status = 'INVALID'
  AND owner IN ('APPS', 'XXCUST')
GROUP BY owner, object_type
ORDER BY count DESC;
```

## Expected Outcomes After Compilation

### Success Indicators
- **90%+ objects recompile successfully** - Normal behavior
- **Remaining invalids have clear dependency errors** - Check DBA_ERRORS for root cause
- **Custom objects invalid, Oracle standard objects valid** - Likely custom code issue

### Failure Indicators (Requires Investigation)
- **Objects still invalid after 2-3 recompile attempts** - Dependency loop or missing grants
- **Core EBS packages invalid (FND, GL, AP, AR)** - Serious issue, contact Oracle Support
- **Incremental growth (new invalids appear daily)** - Background jobs or ETL processes causing issues

## Common Patterns in EBS

### Post-Patch Invalid Objects
After applying EBS patches, expect:
- **10-30 objects** temporarily invalid (normal)
- **Views/Synonyms** most commonly affected
- **Automatic recompilation** during adop cleanup phase
- **Resolve within 24 hours** to avoid impacting scheduled jobs

### ADOP Cycle Invalid Objects
During ADOP (online patching):
- **Edition-specific invalids** expected in patch edition
- **Run fs_clone**: May invalidate objects in run edition
- **Cutover phase**: System recompiles automatically
- **Post-cutover**: Check both RUN and PATCH editions

### After Database Upgrades
- **Hundreds of invalids** expected immediately after upgrade
- **Run utlrp.sql** multiple times (2-3 iterations)
- **Check for Java objects** separately (loadjava issues common)

## Analysis Guidelines for LLM

When analyzing invalid objects data:

1. **Always state the exact count** - Numbers matter for severity
2. **Show real object examples** - Use actual OBJECT_NAME and OBJECT_TYPE from data
3. **Identify patterns** - Are they all PROCEDURE? All from same owner? Created on same date?
4. **Consider Last DDL Time** - Recent objects (<7 days) vs old invalids (>30 days)
5. **Provide actionable SQL** - Give exact commands user can run immediately
6. **Set realistic expectations** - "Run UTL_RECOMP.RECOMP_SERIAL, expect 90%+ to resolve"
7. **Suggest investigation paths** - If >100 objects, check DBA_ERRORS first before compiling
8. **Mention impact** - Which business processes might be affected (e.g., Concurrent programs, APIs)

## Next Steps Template

For any invalid objects finding, always include:

1. **Immediate Action** - SQL to get error details (DBA_ERRORS)
2. **Compilation Command** - Exact syntax for UTL_RECOMP or ALTER ... COMPILE
3. **Verification Query** - SQL to confirm resolution
4. **Escalation Path** - When to engage Oracle Support (e.g., core packages invalid, >500 objects)

## Red Flags (Escalate Immediately)

- **FND_* packages invalid** - Core EBS framework affected
- **AD_* packages invalid** - Applications DBA utilities broken
- **JTF/CRM packages invalid** - Customer relationship management impacted
- **>1000 invalid objects** - Database-level issue, not just app-tier
- **Invalids growing daily** - Active process causing corruption

---

**Note to LLM:** Use this knowledge to provide specific, actionable, EBS-aware analysis of invalid objects. Always reference this domain knowledge when interpreting invalid_objects control results.
