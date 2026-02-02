# Invalid Objects - EBS R12 Knowledge

## Severity Thresholds
- **0-10**: OK (normal post-patch)
- **11-50**: WARN (investigate)
- **51-100**: WARN (requires attention)
- **100+**: CRIT (immediate action)
- **500+**: CRITICAL (major issue)

## Common Causes
- Missing dependencies, grants, synonyms
- Patch/ADOP cycles (temporary)
- Schema changes (ALTER TABLE, etc.)

## Recompilation Commands

**Bulk (Recommended):**
```sql
EXEC UTL_RECOMP.RECOMP_SERIAL('APPS');
EXEC UTL_RECOMP.RECOMP_PARALLEL(4, 'APPS');  -- Parallel
```

**Manual:**
```sql
ALTER PROCEDURE/FUNCTION/PACKAGE/VIEW apps.object_name COMPILE;
ALTER PACKAGE apps.pkg_name COMPILE SPECIFICATION;  -- Then BODY
```

**EBS Script:**
```bash
cd $ADMIN_SCRIPTS_HOME; sqlplus apps/pass @adutlrcmp.sql
```

## Investigation Queries

**Check errors:**
```sql
SELECT owner, name, type, line, text FROM DBA_ERRORS WHERE owner='APPS';
```

**Verify after recompile:**
```sql
SELECT object_type, COUNT(*) FROM DBA_OBJECTS WHERE status='INVALID' AND owner='APPS' GROUP BY object_type;
```

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
LLM Analysis Guidelines

**MUST DO:**
1. State exact count + apply severity threshold
2. Show 3-5 REAL object examples (OBJECT_NAME + OBJECT_TYPE from data)
3. Identify patterns (all PROCEDURE? same owner? recent dates?)
4. Provide UTL_RECOMP command + DBA_ERRORS query
5. Set expectation: "90%+ should resolve after recompile"

**RED FLAGS (Escalate):**
- FND_*/AD_*/GL_*/AP_*/AR_* packages invalid → Core EBS affected
- >1000 objects → Database-level issue
- Growing daily → Active corruption

**Next Steps (Always 3-4 items):**
1. Check errors: `SELECT * FROM DBA_ERRORS WHERE owner='APPS'`
2. Recompile: `EXEC UTL_RECOMP.RECOMP_SERIAL('APPS')`
3. Verify: Check count dropped by 90%+
4. If persistent: Review dependencies or engage Oracle Support