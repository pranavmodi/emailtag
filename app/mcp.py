"""
MCP (Model Context Protocol) Client Module

This module provides MCP client functionality for connecting to and interacting 
with MCP servers. It handles tool discovery, remote tool execution, and connection management.
"""

import asyncio
from typing import Dict, Any, List, Optional
import httpx
from celery.utils.log import get_task_logger
import json
from app.core.config import settings # Import settings

logger = get_task_logger(__name__)


class MCPClient:
    """
    Client for connecting to and interacting with MCP servers.
    
    Handles:
    - Connection to MCP server
    - Tool discovery and listing
    - Remote tool execution
    - Connection cleanup
    """
    
    def __init__(self, server_url: str):
        """
        Initialize MCP client.
        
        Args:
            server_url: URL of the MCP server endpoint
        """
        self.server_url = server_url
        self.available_tools = []
        headers = {
            "Accept": "application/json, text/event-stream"
        }
        # Use 30 second timeout for MCP operations (some tools like get_patient_lien_bill_balance can be slow)
        timeout = httpx.Timeout(30.0, connect=10.0)
        self.client = httpx.AsyncClient(follow_redirects=True, headers=headers, timeout=timeout)
        self._connected = False
    
    async def connect(self) -> bool:
        """
        Connect to MCP server and discover available tools.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            # Get available tools from MCP server
            response = await self.client.post(
                self.server_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {}
                }
            )
            
            if response.status_code == 200:
                if not response.text:
                    logger.error("MCP server returned status 200 but with an empty response body during connect.")
                    return False
                
                response_text = response.text.strip()
                json_data = None

                # Handle Server-Sent Events (SSE) format from streamable MCP servers
                if response_text.startswith('event: message'):
                    for line in response_text.split('\n'):
                        if line.startswith('data:'):
                            json_str = line[len('data:'):].strip()
                            try:
                                json_data = json.loads(json_str)
                                break # Found and parsed the data line
                            except json.JSONDecodeError:
                                logger.error(f"Failed to decode JSON from SSE data line: '{json_str}'")
                                return False
                else:
                    # Fallback for standard JSON response
                    try:
                        json_data = response.json()
                    except json.JSONDecodeError:
                        # This covers the previous error: Failed to decode JSON from MCP server response.
                        logger.error(f"Response was not valid JSON or SSE. Status: 200. Body: '{response_text}'")
                        return False

                if json_data:
                    if "result" in json_data and "tools" in json_data["result"]:
                        self.available_tools = json_data["result"]["tools"]
                        self._connected = True
                        logger.info(f"Connected to MCP server. Available tools: {[tool['name'] for tool in self.available_tools]}")
                        return True
                    else:
                        logger.error(f"MCP server response was valid JSON but not in the expected format: {json_data}")
                        return False
                else:
                    # This case would be hit if SSE format was detected but no 'data:' line was found or parsed
                    logger.error(f"Could not extract JSON data from MCP server response. Body: '{response_text}'")
                    return False

            logger.error(f"Failed to connect to MCP server: {response.status_code} - {response.text}")
            return False
            
        except httpx.RequestError as exc:
            logger.error(f"An HTTP error occurred while requesting {exc.request.url!r}: {exc}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred when connecting to MCP server: {e}", exc_info=True)
            return False
    
    @property
    def is_connected(self) -> bool:
        """Check if client is connected to MCP server."""
        return self._connected
    
    def get_available_tools(self) -> List[Dict[str, Any]]:
        """
        Get list of available tools from the MCP server.
        
        Returns:
            List of tool definitions
        """
        return self.available_tools
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call a tool on the MCP server.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Arguments to pass to the tool
            
        Returns:
            Dictionary containing the tool result or error information
        """
        if not self._connected:
            logger.warning("MCP client not connected. Attempting to connect...")
            if not await self.connect():
                return {"success": False, "error": "MCP server not available"}
        
        try:
            response = await self.client.post(
                self.server_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": arguments
                    }
                }
            )
            
            if response.status_code in (200, 202):
                if not response.text and response.status_code == 202:
                     logger.info(f"MCP tool call '{tool_name}' accepted (202) for async processing.")
                     return {"success": True, "status": "processing_async"}

                if not response.text:
                    logger.error(f"MCP tool call '{tool_name}' returned status {response.status_code} with an empty body.")
                    return {"success": False, "error": f"Tool call returned empty response with status {response.status_code}"}

                response_text = response.text.strip()
                json_rpc_response = None

                # Handle Server-Sent Events (SSE) format
                if response_text.startswith('event: message'):
                    for line in response_text.split('\n'):
                        if line.startswith('data:'):
                            json_str = line[len('data:'):].strip()
                            try:
                                json_rpc_response = json.loads(json_str)
                                break
                            except json.JSONDecodeError:
                                logger.error(f"Failed to decode JSON from SSE data line for tool '{tool_name}': '{json_str}'")
                                return {"success": False, "error": "Invalid SSE JSON from server"}
                else:
                    # Fallback for standard JSON response
                    try:
                        json_rpc_response = response.json()
                    except json.JSONDecodeError:
                        logger.warning(f"Response for tool '{tool_name}' was not JSON or SSE. Returning raw text. Body: '{response_text}'")
                        return {"success": True, "result": response_text}

                if json_rpc_response is None:
                    logger.error(f"Could not extract JSON data from tool '{tool_name}' response: {response_text}")
                    return {"success": False, "error": "Could not extract JSON from response"}

                if "error" in json_rpc_response:
                    logger.error(f"MCP tool call for '{tool_name}' failed with server error: {json_rpc_response['error']}")
                    return {"success": False, "error": json_rpc_response['error']}

                if "result" in json_rpc_response:
                    tool_result = json_rpc_response["result"]
                    final_result = None

                    # Handle the case where the result is wrapped in a 'content' object by the streamable server
                    if isinstance(tool_result, dict) and 'content' in tool_result and isinstance(tool_result['content'], list) and tool_result['content']:
                        if 'text' in tool_result['content'][0]:
                            text_payload = tool_result['content'][0]['text']
                            try:
                                final_result = json.loads(text_payload)
                            except (json.JSONDecodeError, TypeError):
                                logger.warning(f"MCP tool '{tool_name}' content was not valid JSON. Passing as raw text. Content: {text_payload}")
                                final_result = {"success": True, "result": text_payload}
                        else:
                            final_result = tool_result # Not the structure we're looking for, pass it through
                    elif isinstance(tool_result, str):
                        try:
                            # The result itself might be a stringified JSON object
                            final_result = json.loads(tool_result)
                        except json.JSONDecodeError:
                            # Not a JSON string, return the string as is, wrapped in a dict
                            final_result = {"success": True, "result": tool_result}
                    else:
                        final_result = tool_result
                    
                    # Log the raw response structure without base64 content
                    def get_raw_response_keys(obj, max_depth=6, current_depth=0):
                        """Get keys and structure info from raw MCP response, avoiding base64 content."""
                        if current_depth >= max_depth:
                            return f"<max_depth_reached_type_{type(obj).__name__}>"
                        
                        if isinstance(obj, dict):
                            keys_info = {}
                            for k, v in obj.items():
                                if k in ['bill'] and isinstance(v, str) and len(v) > 100:
                                    keys_info[k] = f"<base64_content_length_{len(v)}>"
                                elif isinstance(v, str) and len(v) > 200:
                                    keys_info[k] = f"<string_length_{len(v)}_truncated>"
                                elif isinstance(v, (dict, list)):
                                    keys_info[k] = get_raw_response_keys(v, max_depth, current_depth + 1)
                                else:
                                    keys_info[k] = v
                            return keys_info
                        elif isinstance(obj, list):
                            if len(obj) == 0:
                                return []
                            elif len(obj) <= 2:
                                return [get_raw_response_keys(item, max_depth, current_depth + 1) for item in obj]
                            else:
                                return [get_raw_response_keys(obj[0], max_depth, current_depth + 1), f"<{len(obj)-1}_more_items>"]
                        else:
                            return obj
                    
                    raw_response_structure = get_raw_response_keys(final_result)
                    # logger.info(f"MCP tool '{tool_name}' raw response structure: {raw_response_structure}")
                    
                    # Log the raw response if the final result isn't a dictionary, as this is usually unexpected.
                    if not isinstance(final_result, dict):
                        logger.warning(f"MCP tool '{tool_name}' produced a non-dictionary result of type {type(final_result)}. This may cause issues for the agent. Raw server response: {response.text}")
                    
                    return final_result
                
                logger.error(f"Invalid JSON-RPC response for tool '{tool_name}': {json_rpc_response}")
                return {"success": False, "error": "Invalid JSON-RPC response from server."}
            
            logger.error(f"MCP tool call failed: {response.status_code} - {response.text}")
            return {"success": False, "error": f"MCP tool call failed: {response.status_code}"}
            
        except Exception as e:
            # Handle different types of errors with appropriate log levels
            error_str = str(e)
            if "timeout" in error_str.lower() or "ReadTimeout" in str(type(e)):
                logger.warning(f"MCP tool {tool_name} timed out: {error_str}")
                return {"success": False, "error": f"Tool call timed out: {error_str}"}
            else:
                logger.error(f"Error calling MCP tool {tool_name}: {e}", exc_info=True)
                return {"success": False, "error": f"Error calling MCP tool: {str(e)}"}
    
    async def close(self):
        """Close the MCP client connection."""
        try:
            await self.client.aclose()
            self._connected = False
            logger.info("MCP client connection closed")
        except Exception as e:
            logger.warning(f"Error closing MCP client: {e}")


# Global MCP client instance for shared use
default_mcp_client = MCPClient(server_url=str(settings.MCP_SERVER_URL))


async def get_mcp_client(server_url: Optional[str] = None) -> MCPClient:
    """
    Get an MCP client instance.
    
    Args:
        server_url: Optional custom server URL. If None, uses default client.
        
    Returns:
        MCPClient instance
    """
    if server_url:
        return MCPClient(server_url=server_url)
    return default_mcp_client


# Convenience functions for common operations
async def call_mcp_tool(tool_name: str, arguments: Dict[str, Any], server_url: Optional[str] = None) -> Dict[str, Any]:
    """
    Convenience function to call an MCP tool.
    
    Args:
        tool_name: Name of the tool to call
        arguments: Arguments to pass to the tool
        server_url: Optional custom server URL
        
    Returns:
        Tool result
    """
    client = await get_mcp_client(server_url)
    if not client.is_connected:
        await client.connect()
    
    return await client.call_tool(tool_name, arguments)


async def list_mcp_tools(server_url: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    List available tools from MCP server.
    
    Args:
        server_url: Optional custom server URL
        
    Returns:
        List of available tools
    """
    client = await get_mcp_client(server_url)
    if not client.is_connected:
        await client.connect()
    
    return client.get_available_tools() 