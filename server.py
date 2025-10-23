"""
Roleplay Restaurant Report MCP Server

This MCP server provides tools to query restaurant roleplay task performance data
from the roleplay_daily_reports materialized view in Supabase.

Version: 1.3.0
Created: 2025-10-22
Updated: 2025-10-24 - Enhanced Tool 2 with report-centric description and opening/closing period categorization
Previous: 1.2.2 - Fixed SQL syntax error (removed semicolon from metadata query)
         1.2.1 - Fixed Tool 1 to avoid information_schema
         1.2.0 - Added server-level instructions
         1.1.0 - Enhanced tool descriptions

Tools (MUST be called in order):
1. get_view_schema_and_samples - ⚠️ REQUIRED FIRST: Returns schema and sample data
2. execute_custom_query - Generates comprehensive performance reports with period categorization

WORKFLOW:
- Always call Tool 1 first to understand available columns
- Then use Tool 2 to generate reports with comprehensive data by default

Security: Read-only queries only, SQL injection prevention enforced
"""

import os
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, field_validator
from supabase import create_client, Client

# Load environment variables
load_dotenv()

# Constants
CHARACTER_LIMIT = 25000
VIEW_NAME = "roleplay_daily_reports"
DEFAULT_ROW_LIMIT = 100
MAX_ROW_LIMIT = 1000

# Initialize Supabase client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing required environment variables: SUPABASE_URL or SUPABASE_ANON_KEY")

# Using ANON key - respects RLS policies, safer than service_role key
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Initialize FastMCP server with workflow instructions
mcp = FastMCP(
    name="roleplay-reports",
    instructions="""
This server provides access to restaurant roleplay task performance data.

REQUIRED WORKFLOW - YOU MUST FOLLOW THIS ORDER:
1. 🔍 ALWAYS call get_view_schema_and_samples FIRST to understand the data structure
2. 📊 Then call execute_custom_query with correct column names from step 1

WHY THIS MATTERS:
- All column names are in Chinese and require double quotes in SQL
- Without the schema, you'll write incorrect queries that will fail
- The schema tool shows you all available columns with descriptions

"""
)


# Input validation models
class CustomQueryInput(BaseModel):
    """Input schema for execute_custom_query tool"""

    query: str = Field(
        ...,
        description="SQL SELECT query to execute on roleplay_daily_reports view. Must be a read-only SELECT statement. Use double quotes for Chinese column names like \"餐厅完整名称\".",
        min_length=10,
        max_length=5000,
        examples=[
            'SELECT * FROM roleplay_daily_reports WHERE "运营日期"::date = CURRENT_DATE LIMIT 10',
            'SELECT "餐厅完整名称", "总体任务完成率" FROM roleplay_daily_reports WHERE "餐厅完整名称" ILIKE \'%绵阳%\' ORDER BY "运营日期" DESC LIMIT 20'
        ]
    )

    row_limit: int = Field(
        default=DEFAULT_ROW_LIMIT,
        ge=1,
        le=MAX_ROW_LIMIT,
        description=f"Maximum number of rows to return. Default: {DEFAULT_ROW_LIMIT}, Maximum: {MAX_ROW_LIMIT}"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "query": 'SELECT "餐厅完整名称", "总体任务完成率", "总体任务准时率" FROM roleplay_daily_reports WHERE "运营日期"::date = CURRENT_DATE - 1 ORDER BY "总体任务完成率" DESC',
                    "row_limit": 100
                }
            ]
        }
    }


# Utility functions
def validate_query_safety(query: str) -> tuple[bool, Optional[str]]:
    """
    Validate that query is safe and read-only.

    Returns:
        (is_valid, error_message): Tuple of boolean and optional error message
    """
    query_upper = query.strip().upper()

    # Must start with SELECT
    if not query_upper.startswith('SELECT'):
        return False, "Only SELECT queries are allowed. Your query must start with SELECT."

    # Block dangerous keywords
    dangerous_keywords = [
        'INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'CREATE',
        'TRUNCATE', 'GRANT', 'REVOKE', 'EXEC', 'EXECUTE',
        'PROCEDURE', 'FUNCTION', 'TRIGGER', 'INDEX', 'VIEW',
        'SCHEMA', 'DATABASE', 'TABLE', 'COLUMN', 'INTO'
    ]

    for keyword in dangerous_keywords:
        # Use word boundaries to avoid false positives (e.g., "DELETE" in comments)
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, query_upper):
            return False, f"Keyword '{keyword}' is not allowed. Only read-only SELECT queries are permitted."

    return True, None


def enforce_row_limit(query: str, row_limit: int) -> str:
    """
    Ensure query has a LIMIT clause. Add one if missing or modify if exceeds max.

    Args:
        query: SQL query string
        row_limit: Desired row limit

    Returns:
        Modified query with enforced LIMIT
    """
    query_upper = query.strip().upper()

    # Check if LIMIT already exists
    if 'LIMIT' in query_upper:
        # Extract existing limit
        match = re.search(r'\bLIMIT\s+(\d+)', query_upper)
        if match:
            existing_limit = int(match.group(1))
            if existing_limit > row_limit:
                # Replace with enforced limit
                query = re.sub(
                    r'\bLIMIT\s+\d+',
                    f'LIMIT {row_limit}',
                    query,
                    flags=re.IGNORECASE
                )
    else:
        # Add LIMIT clause
        query = query.strip()
        if query.endswith(';'):
            query = query[:-1]
        query = f"{query} LIMIT {row_limit}"

    return query


def truncate_response(data: Any, max_chars: int = CHARACTER_LIMIT) -> tuple[Any, bool]:
    """
    Truncate response data if it exceeds character limit.

    Args:
        data: Response data to truncate
        max_chars: Maximum character limit

    Returns:
        (truncated_data, was_truncated): Tuple of data and truncation flag
    """
    json_str = json.dumps(data, ensure_ascii=False, indent=2)

    if len(json_str) <= max_chars:
        return data, False

    # Truncate rows if data is a list
    if isinstance(data, list) and len(data) > 1:
        # Binary search to find optimal row count
        left, right = 1, len(data)
        result_rows = 1

        while left <= right:
            mid = (left + right) // 2
            test_data = data[:mid]
            test_str = json.dumps(test_data, ensure_ascii=False, indent=2)

            if len(test_str) <= max_chars:
                result_rows = mid
                left = mid + 1
            else:
                right = mid - 1

        return data[:result_rows], True

    return data, True


def format_error_response(
    error_type: str,
    message: str,
    suggestion: Optional[str] = None
) -> Dict[str, Any]:
    """
    Format error response in consistent JSON structure.

    Args:
        error_type: Type of error (e.g., "QueryValidationError", "DatabaseError")
        message: Error message
        suggestion: Optional suggestion for user

    Returns:
        Formatted error response dictionary
    """
    response = {
        "success": False,
        "error": {
            "type": error_type,
            "message": message
        }
    }

    if suggestion:
        response["error"]["suggestion"] = suggestion

    return response


# MCP Tool Implementations

@mcp.tool(
    description="""⚠️ REQUIRED FIRST STEP - Always call this tool before executing any queries!

🔍 Get complete schema and sample data from roleplay_daily_reports view.

WORKFLOW:
1. 👉 Call this tool FIRST to understand available columns
2. Then use execute_custom_query with correct column names

This tool returns:
- All columns' definitions (Chinese names, English names, data types, descriptions)
- 5 most recent sample records
- Database metadata (row count, date range, restaurant list)
- SQL query usage hints

IMPORTANT: All column names are in Chinese and require double quotes in queries.
Example: "餐厅完整名称", "总体任务完成率"

获取 roleplay_daily_reports 视图的完整结构和示例数据。

返回格式: JSON object with schema, samples, metadata, and usage hints"""
)
def get_view_schema_and_samples() -> Dict[str, Any]:
    """
    Get complete schema information and sample data from roleplay_daily_reports view.

    This tool provides AI agents with all necessary context about the database view
    including column definitions, sample data, and query usage hints.

    Returns:
        JSON response containing:
        - view_name: Name of the materialized view
        - description: Brief description of the view
        - columns: List of all columns with names, types, and descriptions
        - sample_data: 5 most recent records
        - metadata: Statistics about the data (row count, date range, restaurants)
        - usage_hints: Example SQL queries for common patterns

    Raises:
        Exception: If database query fails
    """
    try:
        # 1. Get sample data first (we'll use it to get column names)
        sample_query = f'SELECT * FROM {VIEW_NAME} ORDER BY "运营日期" DESC LIMIT 5'
        sample_result = supabase.rpc('execute_sql', {'query': sample_query}).execute()
        sample_data = sample_result.data if hasattr(sample_result, 'data') else []

        # Extract column names from sample data (first row's keys)
        actual_columns = list(sample_data[0].keys()) if sample_data and len(sample_data) > 0 else []

        # Parse column data with descriptions
        columns = []
        column_mapping = {
            "报表唯一标识": ("report_id", "每条记录的唯一标识"),
            "运营日期": ("operating_date", "报表对应的运营日期"),
            "餐厅ID": ("restaurant_id", "餐厅的唯一标识"),
            "餐厅完整名称": ("restaurant_name", "餐厅名称（品牌-城市-门店）"),
            "总任务数量": ("total_tasks", "当天所有任务的总数"),
            "已完成任务数量": ("completed_tasks", "当天已完成的任务数量"),
            "总体任务完成率": ("overall_completion_rate", "总体任务完成百分比 (0-100)"),
            "总体任务准时率": ("overall_ontime_rate", "总体任务准时完成百分比 (0-100)"),
            "店长总任务数量": ("manager_total_tasks", "店长角色的总任务数"),
            "店长已完成任务数量": ("manager_completed_tasks", "店长已完成的任务数"),
            "店长任务完成率": ("manager_completion_rate", "店长任务完成百分比"),
            "店长任务准时率": ("manager_ontime_rate", "店长任务准时完成百分比"),
            "值班经理总任务数量": ("duty_manager_total_tasks", "值班经理角色的总任务数"),
            "值班经理已完成任务数量": ("duty_manager_completed_tasks", "值班经理已完成的任务数"),
            "值班经理任务完成率": ("duty_manager_completion_rate", "值班经理任务完成百分比"),
            "值班经理任务准时率": ("duty_manager_ontime_rate", "值班经理任务准时完成百分比"),
            "厨师总任务数量": ("chef_total_tasks", "厨师角色的总任务数"),
            "厨师已完成任务数量": ("chef_completed_tasks", "厨师已完成的任务数"),
            "厨师任务完成率": ("chef_completion_rate", "厨师任务完成百分比"),
            "厨师任务准时率": ("chef_ontime_rate", "厨师任务准时完成百分比"),
            "手动闭店任务是否完成": ("manual_closing_completed", "手动闭店任务的完成状态 (true/false)"),
            "闭店任务ID": ("closing_task_id", "闭店任务的唯一标识"),
        }

        # Build column list from actual data
        for col_name in actual_columns:
            english_name, description = column_mapping.get(col_name, (col_name, "列数据"))

            # Infer data type from sample data
            data_type = "unknown"
            if sample_data and len(sample_data) > 0:
                value = sample_data[0].get(col_name)
                if value is not None:
                    if isinstance(value, bool):
                        data_type = "boolean"
                    elif isinstance(value, int):
                        data_type = "integer"
                    elif isinstance(value, float):
                        data_type = "numeric"
                    elif isinstance(value, str):
                        data_type = "text"
                    else:
                        data_type = "unknown"

            columns.append({
                "name": col_name,
                "name_english": english_name,
                "data_type": data_type,
                "description": description
            })

        # 2. Get metadata
        metadata_query = f"""
        SELECT
            COUNT(*) as total_rows,
            MIN("运营日期") as earliest_date,
            MAX("运营日期") as latest_date,
            COUNT(DISTINCT "餐厅ID") as restaurant_count
        FROM {VIEW_NAME}
        """
        metadata_result = supabase.rpc('execute_sql', {'query': metadata_query}).execute()
        metadata_raw = metadata_result.data[0] if hasattr(metadata_result, 'data') and metadata_result.data else {}

        # Get distinct restaurant names
        restaurant_query = f'SELECT DISTINCT "餐厅完整名称" FROM {VIEW_NAME} ORDER BY "餐厅完整名称"'
        restaurant_result = supabase.rpc('execute_sql', {'query': restaurant_query}).execute()
        restaurants = [r.get('餐厅完整名称', '') for r in (restaurant_result.data if hasattr(restaurant_result, 'data') else [])]

        # Build response
        response = {
            "success": True,
            "view_name": VIEW_NAME,
            "description": "餐厅角色扮演任务日报数据 - 57个KPI指标，涵盖总体、角色、时段维度的任务完成情况",
            "columns": columns,
            "sample_data": sample_data,
            "metadata": {
                "total_rows": metadata_raw.get('total_rows', 0),
                "date_range": {
                    "earliest": str(metadata_raw.get('earliest_date', '')),
                    "latest": str(metadata_raw.get('latest_date', ''))
                },
                "restaurant_count": metadata_raw.get('restaurant_count', 0),
                "restaurants": restaurants
            },
            "usage_hints": [
                '查询时使用中文列名并加双引号: SELECT "餐厅完整名称", "总体任务完成率" FROM roleplay_daily_reports',
                '日期过滤: WHERE "运营日期"::date = \'2025-10-21\'',
                '模糊搜索餐厅: WHERE "餐厅完整名称" ILIKE \'%绵阳%\'',
                '排除零任务: WHERE "总任务数量" > 0',
                '按完成率排序: ORDER BY "总体任务完成率" DESC',
                '聚合查询: SELECT AVG("总体任务完成率") FROM roleplay_daily_reports WHERE ...',
                '分组统计: GROUP BY "餐厅完整名称"'
            ]
        }

        # Truncate if needed
        truncated_response, was_truncated = truncate_response(response)
        if was_truncated:
            truncated_response["_truncated"] = True
            truncated_response["_message"] = f"Response was truncated to fit within {CHARACTER_LIMIT} character limit"

        return truncated_response

    except Exception as e:
        return format_error_response(
            error_type="DatabaseError",
            message=f"Failed to retrieve schema and samples: {str(e)}",
            suggestion="Please check database connection and ensure the roleplay_daily_reports view exists."
        )


@mcp.tool(
    description="""⚠️ PREREQUISITE: Must call get_view_schema_and_samples FIRST before using this tool!

Execute custom SQL queries to generate comprehensive performance reports from the
roleplay_daily_reports materialized view.

**Report Philosophy**: When users request a report, fetch ALL available columns
for the specified scope. The view contains 57 pre-calculated KPI metrics across
overall, role-based, and period-based dimensions.

**Query Guidelines**:
- Daily report: SELECT * for single date
- Weekly/Monthly: SELECT * for date range (or aggregate with AVG/SUM)
- Multi-restaurant: Include all restaurants, optionally GROUP BY restaurant
- Let SQL do the filtering (WHERE clause), return comprehensive data

**Period Categorizations** (for opening/closing questions):
- 开市 (Opening): 开店时段, 午市准备时段, 晚市准备时段
  (Setup tasks BEFORE guest service)
- 闭市 (Closing): 午市收市时段, 收市打烊时段
  (Cleanup tasks AFTER service ends)

**Common Patterns**:
- Single restaurant daily: WHERE "餐厅完整名称" ILIKE '%name%' AND "运营日期"::date = 'YYYY-MM-DD'
- Weekly trend: date BETWEEN start AND end, optionally AVG() for summary
- Multi-restaurant comparison: Omit restaurant filter, GROUP BY "餐厅完整名称"
- Opening/closing analysis: Use period columns (开店时段任务完成率, etc.)

**Security**: SELECT-only, max 1000 rows, 25k character limit applies.

Parameters:
- query: SQL SELECT statement (required)
- row_limit: Max rows to return (default 100, max 1000)

在 roleplay_daily_reports 视图上执行自定义SQL查询以生成综合性能报告。

返回格式: JSON object with success flag, query, row count, execution time, and data"""
)
def execute_custom_query(query: str, row_limit: int = DEFAULT_ROW_LIMIT) -> Dict[str, Any]:
    """
    Execute a custom SQL SELECT query on the roleplay_daily_reports view.

    This tool enables flexible querying with automatic safety validation,
    row limiting, and response truncation.

    Args:
        query: SQL SELECT query to execute. Must be read-only.
        row_limit: Maximum number of rows to return (default 100, max 1000)

    Returns:
        JSON response containing:
        - success: Boolean indicating query success
        - query: The executed query (with enforced LIMIT)
        - row_count: Number of rows returned
        - execution_time_ms: Query execution time in milliseconds
        - data: Query results as list of dictionaries

        On error:
        - success: False
        - error: Object with type, message, and suggestion

    Security:
        - Only SELECT queries allowed
        - Dangerous keywords (INSERT, UPDATE, DELETE, etc.) blocked
        - Row limits enforced automatically
        - SQL injection prevention through Supabase client
    """
    start_time = datetime.now()

    try:
        # Validate query safety
        is_valid, error_msg = validate_query_safety(query)
        if not is_valid:
            return format_error_response(
                error_type="QueryValidationError",
                message=error_msg,
                suggestion='请使用 SELECT 查询，例如: SELECT "餐厅完整名称", "总体任务完成率" FROM roleplay_daily_reports WHERE "运营日期"::date = CURRENT_DATE - 1'
            )

        # Enforce row limit
        validated_query = enforce_row_limit(query, min(row_limit, MAX_ROW_LIMIT))

        # Execute query via Supabase
        result = supabase.rpc('execute_sql', {'query': validated_query}).execute()

        # Calculate execution time
        end_time = datetime.now()
        execution_time_ms = int((end_time - start_time).total_seconds() * 1000)

        # Extract data
        data = result.data if hasattr(result, 'data') else []
        row_count = len(data)

        # Build response
        response = {
            "success": True,
            "query": validated_query,
            "row_count": row_count,
            "execution_time_ms": execution_time_ms,
            "data": data
        }

        # Truncate if needed
        truncated_response, was_truncated = truncate_response(response)
        if was_truncated:
            truncated_response["_truncated"] = True
            truncated_response["_message"] = f"Response was truncated to fit within {CHARACTER_LIMIT} character limit. Original row count: {row_count}"

        return truncated_response

    except Exception as e:
        return format_error_response(
            error_type="DatabaseError",
            message=f"Query execution failed: {str(e)}",
            suggestion="请检查SQL语法是否正确，特别注意中文列名需要使用双引号。可以先调用 get_view_schema_and_samples 查看可用的列名。"
        )


# Run the server
if __name__ == "__main__":
    mcp.run()
