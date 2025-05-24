import logging
import mcp.server.stdio
from typing import Annotated
from mcp.server import Server
from .requestor import request_data
from pydantic import BaseModel, Field
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import McpError
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.types import (
    GetPromptResult,
    Prompt,
    PromptArgument,
    PromptMessage,
    TextContent,
    Tool,
    INVALID_PARAMS,
    INTERNAL_ERROR,
)


logging.basicConfig(
    level=logging.DEBUG, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)

server = Server("mslocalrag")

class Query(BaseModel):
    text: Annotated[
        str, 
        Field(description="Nội dung cần tìm kiếm")
    ]
    max_results: Annotated[
        int | None, 
        Field(description="Số lượng kết quả tối đa")
    ] = None
    file_type: Annotated[
        str | None, 
        Field(description="Loại tệp cần tìm kiếm")
    ] = None
    format: Annotated[
        str | None, 
        Field(description="Định dạng kết quả mong muốn")
    ] = None

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="mslocalrag-query",
            description="Tìm kiếm thông tin trong các tệp cục bộ (PDF, CSV, DOCX, MD, TXT)",
            inputSchema=Query.model_json_schema(),
        ),
        Tool(
            name="mslocalrag-enhanced-query",
            description="Tìm kiếm thông tin nâng cao với khả năng phân tích ngữ cảnh",
            inputSchema=Query.model_json_schema(),
        )
    ]
    
@server.list_prompts()
async def list_prompts() -> list[Prompt]:
    logging.info("List of prompts")
    return [
        Prompt(
            name="mslocalrag-query",
            description="Tìm kiếm thông tin trong các tệp cục bộ",
            arguments=[
                PromptArgument(
                    name="context", description="Nội dung cần tìm kiếm", required=True
                ),
                PromptArgument(
                    name="max_results", description="Số lượng kết quả tối đa", required=False
                ),
                PromptArgument(
                    name="file_type", description="Loại tệp cần tìm kiếm (pdf, docx, txt, ...)", required=False
                )
            ]
        ),
        Prompt(
            name="mslocalrag-enhanced-query",
            description="Tìm kiếm thông tin nâng cao trong các tệp cục bộ",
            arguments=[
                PromptArgument(
                    name="text", description="Câu hỏi hoặc yêu cầu tìm kiếm", required=True
                ),
                PromptArgument(
                    name="context", description="Bối cảnh bổ sung cho câu hỏi", required=False
                ),
                PromptArgument(
                    name="format", description="Định dạng kết quả mong muốn", required=False
                )
            ]
        )            
    ]
    
@server.call_tool()
async def call_tool(name, arguments: dict) -> list[TextContent]:
    if name != "mslocalrag-query":
        logging.error(f"Unknown tool: {name}")
        raise ValueError(f"Unknown tool: {name}")

    logging.info(f"Calling tool: {name} with arguments: {arguments}")
    try:
        args = Query(**arguments)
    except ValueError as e:
        logging.error(str(e))
        raise McpError(INVALID_PARAMS, str(e))
        
    context = args.text
    logging.info(f"Context: {context}")
    if not context:
        logging.error("Context is required")
        raise McpError(INVALID_PARAMS, "Context is required")

    # Thêm xử lý cho các tham số bổ sung
    additional_params = {}
    for key, value in arguments.items():
        if key != "text":
            additional_params[key] = value
    
    # Ghi log các tham số bổ sung
    if additional_params:
        logging.info(f"Additional parameters for tool call: {additional_params}")

    output = await request_data(context)
    if "error" in output:
        logging.error(output["error"])
        raise McpError(INTERNAL_ERROR, output["error"])
    
    logging.info(f"Tool result: {output}")    
    result_output = output['result']['output']
    
    # Tạo kết quả chi tiết hơn
    result = []
    result.append(TextContent(type="text", text=result_output))
    
    # Thêm thông tin về các liên kết nếu có
    if "links" in output['result']:
        links_text = "\n\nTài liệu liên quan:\n" + "\n".join(output['result']['links'])
        result.append(TextContent(type="text", text=links_text))
    
    return result
    
@server.get_prompt()
async def get_prompt(name: str, arguments: dict | None) -> GetPromptResult:
    if not arguments:
        logging.error("Arguments are required")
        raise McpError(INVALID_PARAMS, "Arguments are required")
        
    # Kiểm tra xem có tham số 'context' hoặc 'text' không
    context = None
    if "context" in arguments:
        context = arguments["context"]
    elif "text" in arguments:
        context = arguments["text"]
    else:
        logging.error("Context or text parameter is required")
        raise McpError(INVALID_PARAMS, "Context or text parameter is required")

    # Thêm xử lý cho các tham số bổ sung nếu có
    additional_params = {}
    for key, value in arguments.items():
        if key not in ["context", "text"]:
            additional_params[key] = value
    
    # Ghi log các tham số bổ sung
    if additional_params:
        logging.info(f"Additional parameters: {additional_params}")

    output = await request_data(context)
    if "error" in output:
        error = output["error"]
        logging.error(error)
        return GetPromptResult(
            description=f"Không tìm thấy nội dung cho {context}",
            messages=[
                PromptMessage(
                    role="user", 
                    content=TextContent(type="text", text=error),
                )
            ]
        )

    logging.info(f"Get prompt: {output}")    
    result_output = output['result']['output']
    
    # Tạo mô tả chi tiết hơn cho prompt
    description = f"Đã tìm thấy nội dung cho '{context}'"
    if "links" in output['result']:
        description += f" với {len(output['result']['links'])} tài liệu liên quan"
    
    return GetPromptResult(
        description=description,
        messages=[
            PromptMessage(
                role="user", 
                content=TextContent(type="text", text=result_output)
            )
        ]
    )

async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="mslocalrag",
                server_version="0.0.1",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
