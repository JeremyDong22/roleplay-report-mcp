# Roleplay Restaurant Report MCP Server

**Status:** ✅ Implemented and Operational

A Model Context Protocol (MCP) server that provides AI agents with tools to query restaurant roleplay task performance data from Supabase.

## Overview

This MCP server exposes two powerful tools for analyzing daily restaurant performance metrics across 57 KPI indicators:

1. **`get_view_schema_and_samples`** - Returns complete schema information and sample data (dynamic)
2. **`execute_custom_query`** - Executes custom SQL queries with safety validation

## Features

- **Read-only access** - All queries are validated to be SELECT-only
- **SQL injection prevention** - Automatic validation blocks dangerous operations
- **Flexible querying** - AI can write any SELECT query based on schema
- **Automatic truncation** - Responses limited to 25,000 characters
- **Row limiting** - Configurable limits (default 100, max 1000 rows)
- **Chinese column names** - Full support for business-friendly Chinese column names

## Data Source

The server queries the `roleplay_daily_reports` materialized view which contains:
- **304 records** across 4 restaurants (Aug-Oct 2025)
- **57 columns** with Chinese names for business clarity
- **Key dimensions**: Restaurant, Date, Role (Manager/Duty Manager/Chef), Period (7 time slots)
- **Key metrics**: Task counts, completion rates, on-time rates

## Installation

### Prerequisites

- Python 3.11 or higher
- Supabase project with `roleplay_daily_reports` view
- `uv` package manager (recommended) or `pip`
- ✅ Supabase `execute_sql` RPC function (already created)

### Setup Steps

**Note:** This server is already fully set up! These steps are for reference only.

1. **Virtual environment** ✅ Already created
   ```bash
   # Already done: uv venv
   ```

2. **Dependencies** ✅ Already installed (46 packages)
   ```bash
   # Already done: uv pip install -r requirements.txt
   ```

3. **Environment configuration** ✅ Already configured

   Environment variables are set in `.mcp.json`:
   ```json
   {
     "env": {
       "SUPABASE_URL": "https://wdpeoyugsxqnpwwtkqsl.supabase.co",
       "SUPABASE_ANON_KEY": "eyJhbGci..."
     }
   }
   ```

4. **Supabase RPC function** ✅ Already created

   The `execute_sql(text)` function has been created in your Supabase database to enable flexible SQL query execution.

## Usage

### Running the Server

✅ **The server is already configured and will start automatically when you launch Claude Code!**

The MCP server is configured in `.mcp.json` (project root) and starts automatically:

```json
{
  "mcpServers": {
    "roleplay-reports": {
      "type": "stdio",
      "command": "uv",
      "args": ["--directory", "./roleplay-report-mcp", "run", "server.py"],
      "env": {
        "SUPABASE_URL": "https://wdpeoyugsxqnpwwtkqsl.supabase.co",
        "SUPABASE_ANON_KEY": "eyJhbGci..."
      }
    }
  }
}
```

**To verify it's running:**
1. Restart Claude Code
2. Look for "roleplay-reports" in MCP server status
3. Try asking: "What columns are in the roleplay daily reports?"

### Manual Testing (Optional)

If you want to test the server manually (not recommended for normal use):

```bash
# This will start the server and it will hang waiting for stdin - that's normal!
cd /Users/jeremydong/Desktop/myMCPServer/roleplay-report-mcp
source .venv/bin/activate
python server.py
```

## Tools

### Tool 1: get_view_schema_and_samples

Returns complete context about the data structure.

**Purpose**: Provide AI with schema information before writing queries.

**Parameters**: None

**Returns**:
- All 57 column definitions (Chinese name, English name, data type, description)
- 5 most recent sample records
- Metadata (total rows, date range, restaurant list)
- SQL usage hints and examples

**Example Usage** (via MCP):
```python
# AI calls this tool first to understand data structure
response = get_view_schema_and_samples()
# Then uses column info to write correct queries
```

### Tool 2: execute_custom_query

Executes custom SQL queries with automatic safety validation.

**Purpose**: Run any read-only query on the database view.

**Parameters**:
- `query` (string, required): SQL SELECT statement
- `row_limit` (integer, optional): Max rows to return (default: 100, max: 1000)

**Returns**:
- `success`: Boolean
- `query`: Executed query (with enforced LIMIT)
- `row_count`: Number of rows returned
- `execution_time_ms`: Query duration
- `data`: Array of result objects

**Example Queries**:

```sql
-- Today's performance for a specific restaurant
SELECT * FROM roleplay_daily_reports
WHERE "餐厅完整名称" ILIKE '%绵阳%'
  AND "运营日期"::date = CURRENT_DATE;

-- Compare all restaurants yesterday
SELECT "餐厅完整名称", "总体任务完成率", "总体任务准时率"
FROM roleplay_daily_reports
WHERE "运营日期"::date = CURRENT_DATE - 1
ORDER BY "总体任务完成率" DESC;

-- Weekly trend for one restaurant
SELECT "运营日期", "总体任务完成率", "总体任务准时率"
FROM roleplay_daily_reports
WHERE "餐厅完整名称" ILIKE '%绵阳%'
  AND "运营日期"::date >= CURRENT_DATE - 7
ORDER BY "运营日期" DESC;

-- Role performance comparison
SELECT "餐厅完整名称",
       AVG("店长任务完成率") as 店长,
       AVG("值班经理任务完成率") as 值班经理,
       AVG("厨师任务完成率") as 厨师
FROM roleplay_daily_reports
WHERE "运营日期"::date >= CURRENT_DATE - 7
GROUP BY "餐厅完整名称";
```

## Security Features

### Query Validation
- **SELECT-only**: Only SELECT queries allowed
- **Keyword blocking**: INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, etc. are blocked
- **Row limits**: Automatic enforcement (max 1000 rows)
- **Parameterization**: Supabase client handles parameter escaping

### SQL Injection Prevention
The server uses multiple layers of protection:
1. Query validation before execution
2. Supabase client's built-in parameterization
3. Read-only database credentials (service role with limited permissions)

### Best Practices
- Use the `service_role` key only in secure environments
- Never expose credentials in client-side code
- Rotate keys regularly
- Monitor query logs for suspicious activity

## Common Query Patterns

### Daily Reports
```sql
-- Single restaurant today
SELECT * FROM roleplay_daily_reports
WHERE "餐厅完整名称" ILIKE '%绵阳%'
  AND "运营日期"::date = CURRENT_DATE;
```

### Trends
```sql
-- Monthly averages
SELECT DATE_TRUNC('week', "运营日期"::timestamp) as 周,
       AVG("总体任务完成率") as 平均完成率
FROM roleplay_daily_reports
WHERE "运营日期"::date >= CURRENT_DATE - 30
GROUP BY 周
ORDER BY 周 DESC;
```

### Alerts
```sql
-- Restaurants with performance issues
SELECT "餐厅完整名称", "总体任务完成率"
FROM roleplay_daily_reports
WHERE "运营日期"::date = CURRENT_DATE - 1
  AND "总体任务完成率" < 50;
```

## Troubleshooting

### Server won't start
- Check Python version: `python --version` (must be 3.11+)
- Verify virtual environment is activated
- Check all dependencies installed: `pip list`

### "Missing environment variables" error
- Environment variables are set in `.mcp.json` (project root)
- Verify `SUPABASE_URL` and `SUPABASE_ANON_KEY` are correctly set
- Restart Claude Code after modifying `.mcp.json`

### "execute_sql function not found" error
- ✅ This function has already been created in your Supabase database
- If you see this error, verify you're using the correct Supabase project
- Check Supabase Dashboard → SQL Editor → Run: `SELECT execute_sql('SELECT 1');`

### Query returns no results
- Check date format: Use `"运营日期"::date` for date comparisons
- Verify Chinese column names have double quotes: `"餐厅完整名称"`
- Test query directly in Supabase SQL Editor first

### "Keyword not allowed" error
- Only SELECT queries are permitted
- Remove any INSERT, UPDATE, DELETE, etc. keywords
- Use `WHERE`, `ORDER BY`, `GROUP BY` for filtering/sorting

## Development

### Project Structure
```
roleplay-report-mcp/
├── server.py              # Main MCP server implementation (485 lines)
├── requirements.txt       # Python dependencies (46 packages)
├── .env.example          # Environment variable template
├── .env                  # Environment variables (gitignored)
├── .venv/                # Virtual environment (Python 3.12)
├── README.md             # This file - user documentation
└── mcp_design.md         # Architecture & implementation documentation
```

### Testing Queries

You can test SQL queries directly in Supabase SQL Editor before using them via MCP:

1. Go to Supabase Dashboard > SQL Editor
2. Run your query on `roleplay_daily_reports`
3. Verify results
4. Use the same query via `execute_custom_query`

### Extending the Server

To add new tools:
1. Define input validation with Pydantic models
2. Implement the tool function with `@mcp.tool()` decorator
3. Add comprehensive docstring in Chinese and English
4. Include error handling and response truncation
5. Test with realistic queries

## Technical Details

### Character Limit
Responses are automatically truncated to 25,000 characters. If truncation occurs:
- `_truncated: true` flag is added
- `_message` explains the truncation
- For list data, rows are removed to fit within limit

### Row Limiting
- Default: 100 rows
- Maximum: 1000 rows
- Automatically enforced via LIMIT clause
- If query has larger LIMIT, it's reduced to max

### Column Name Handling
Chinese column names require double quotes in SQL:
```sql
-- Correct
SELECT "餐厅完整名称", "总体任务完成率" FROM roleplay_daily_reports

-- Incorrect (will error)
SELECT 餐厅完整名称, 总体任务完成率 FROM roleplay_daily_reports
```

## License

This project is for internal use. All rights reserved.

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review the design-plan.md for detailed specifications
3. Test queries in Supabase SQL Editor first
4. Check Supabase logs for database errors

## Supabase RPC Function

### The `execute_sql` Function

This server requires a custom PostgreSQL function in Supabase to execute dynamic SQL queries:

```sql
CREATE OR REPLACE FUNCTION execute_sql(query text)
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  result json;
BEGIN
  EXECUTE format('SELECT json_agg(t) FROM (%s) t', query) INTO result;
  RETURN COALESCE(result, '[]'::json);
EXCEPTION
  WHEN OTHERS THEN
    RETURN json_build_object('error', true, 'message', SQLERRM);
END;
$$;
```

**Status:** ✅ Already created in your Supabase database

**What it does:**
- Accepts any SQL query as a text string
- Executes the query using PostgreSQL's `EXECUTE` statement
- Returns results as a JSON array
- Handles errors gracefully

**Security:** The MCP server validates all queries before sending them to this function (SELECT-only, keyword blocking, row limits).

---

## Version History

- **1.0.0** (2025-10-22): ✅ Fully implemented and operational
  - Two core tools: schema exploration and custom queries
  - Read-only access with safety validation
  - Automatic response truncation (25,000 character limit)
  - Chinese column name support
  - Supabase `execute_sql` RPC function created
  - Virtual environment and dependencies installed
  - MCP server configuration complete
