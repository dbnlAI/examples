from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
import json
from collections import defaultdict
from datetime import datetime

# Model pricing in USD per 1M tokens (prompt / completion)
# Source: https://ai.google.dev/pricing
MODEL_PRICING = {
    'gemini-2.5-flash': {'prompt': 0.075, 'completion': 0.30},  # Per 1M tokens
    'gemini-2.0-flash': {'prompt': 0.075, 'completion': 0.30},
    'gemini-1.5-pro': {'prompt': 1.25, 'completion': 5.00},
    'gemini-1.5-flash': {'prompt': 0.075, 'completion': 0.30},
    'gemini-pro': {'prompt': 0.50, 'completion': 1.50},
    'gemini-flash': {'prompt': 0.075, 'completion': 0.30},
    # OpenAI models
    'gpt-4': {'prompt': 30.00, 'completion': 60.00},
    'gpt-4-turbo': {'prompt': 10.00, 'completion': 30.00},
    'gpt-3.5-turbo': {'prompt': 0.50, 'completion': 1.50},
    # Anthropic Claude models
    'claude-3-opus': {'prompt': 15.00, 'completion': 75.00},
    'claude-3-sonnet': {'prompt': 3.00, 'completion': 15.00},
    'claude-3-haiku': {'prompt': 0.25, 'completion': 1.25},
}


class DBNLSemConvFileExporter(SpanExporter):
    def __init__(self, file_path):
        self.file_path = file_path
        self.file = open(file_path, 'a')
        self.traces = defaultdict(list)  # Group spans by trace_id

    def export(self, spans):
        # First pass: collect all spans by trace_id with their metadata
        spans_by_trace = defaultdict(list)
        span_data_by_id = {}  # Store span data for parent lookups

        for span in spans:
            trace_id = format(span.context.trace_id, '032x')
            span_id = format(span.context.span_id, '016x')
            parent_span_id = format(span.parent.span_id, '016x') if span.parent else None

            # Store span data for later parent lookups
            # Properly extract attributes from OpenTelemetry span
            attrs = {}
            if span.attributes:
                try:
                    # Try to convert to dict (works for most cases)
                    attrs = dict(span.attributes)
                except (TypeError, AttributeError):
                    # Fallback: iterate over items if it's a mapping-like object
                    try:
                        for key, value in span.attributes.items():
                            attrs[key] = value
                    except (TypeError, AttributeError):
                        attrs = {}

            span_data_by_id[span_id] = {
                'span': span,
                'span_id': span_id,
                'parent_span_id': parent_span_id,
                'trace_id': trace_id,
                'attributes': attrs
            }

            spans_by_trace[trace_id].append(span_id)

        # Second pass: process each span with access to parent data
        for span_id, span_data in span_data_by_id.items():
            span = span_data['span']
            trace_id = span_data['trace_id']
            parent_span_id = span_data['parent_span_id']
            attributes_dict = span_data['attributes']

            trace_state = span.context.trace_state.to_header() if hasattr(span.context, 'trace_state') and span.context.trace_state else ""

            # Map status code: UNSET -> OK if completed successfully, ERROR stays ERROR
            raw_status = span.status.status_code.name if span.status else "UNSET"
            if raw_status == "UNSET" and span.end_time:
                status_code = "OK"
            elif raw_status == "ERROR":
                status_code = "ERROR"
            else:
                status_code = raw_status

            status_message = span.status.description if span.status and span.status.description else ""

            # Check if this is a tool execution and if the tool response contains an error
            if attributes_dict.get('gen_ai.operation.name') == 'execute_tool':
                tool_response_str = attributes_dict.get('gcp.vertex.agent.tool_response', '{}')
                try:
                    tool_response = json.loads(tool_response_str)
                    if isinstance(tool_response, dict) and tool_response.get('status') == 'error':
                        status_code = "ERROR"
                        status_message = tool_response.get('status_message', 'Tool execution failed')
                except (json.JSONDecodeError, ValueError):
                    pass

            # Convert timestamps from nanoseconds to ISO 8601 format
            start_time = self._format_timestamp(span.start_time) if span.start_time else None
            end_time = self._format_timestamp(span.end_time) if span.end_time else None

            # Determine OpenInference span kind
            openinference_kind = self._determine_openinference_kind(span, attributes_dict)

            # Extract only OpenInference attributes
            openinference_attributes = self._extract_openinference_attributes(
                span, attributes_dict, openinference_kind
            )

            # Add openinference.span.kind attribute
            openinference_attributes['openinference.span.kind'] = openinference_kind

            # Convert attributes to map<string, string>
            attributes = self._convert_attributes_to_string_map(openinference_attributes)
            # Convert to list of key-value pairs
            attributes = self._dict_to_key_value_list(attributes)

            # Format events
            events = [
                {
                    "timestamp": self._format_timestamp(event.timestamp),
                    "name": event.name,
                    "attributes": self._dict_to_key_value_list(
                        self._convert_attributes_to_string_map(dict(event.attributes) if event.attributes else {})
                    )
                }
                for event in span.events
            ] if span.events else []

            # Format links
            links = [
                {
                    "trace_id": format(link.context.trace_id, '032x'),
                    "span_id": format(link.context.span_id, '016x'),
                    "trace_state": link.context.trace_state.to_header() if hasattr(link.context, 'trace_state') and link.context.trace_state else "",
                    "attributes": self._dict_to_key_value_list(
                        self._convert_attributes_to_string_map(dict(link.attributes) if link.attributes else {})
                    )
                }
                for link in span.links
            ] if span.links else []

            oi_span = {
                "trace_id": trace_id,
                "span_id": span_id,
                "trace_state": trace_state,
                "parent_span_id": parent_span_id,
                "name": span.name,
                "kind": openinference_kind,
                "start_time": start_time,
                "end_time": end_time,
                "attributes": attributes,
                "events": events,
                "links": links,
                "status": {
                    "code": status_code,
                    "message": status_message
                }
            }

            self.traces[trace_id].append(oi_span)

        # Write complete traces (when root span ends, or force write all)
        for trace_id, trace_spans in list(self.traces.items()):
            # Check if this batch contains a root span (no parent_span_id)
            has_root = any(s['parent_span_id'] is None for s in trace_spans)

            if has_root:
                # Bubble up input/output attributes to root span
                self._add_root_span_io_attributes(trace_spans)

                self._write_trace(trace_id, trace_spans)
                # Clear written trace
                del self.traces[trace_id]

        return SpanExportResult.SUCCESS

    def _add_root_span_io_attributes(self, trace_spans):
        """Add input.value, input.mime_type, output.value, output.mime_type to all ancestor spans"""
        # Build a map of span_id -> span for easy lookup
        span_map = {span['span_id']: span for span in trace_spans}

        # Sort spans by start_time for chronological order
        sorted_spans = sorted(trace_spans, key=lambda s: s.get('start_time', ''))

        # Find first LLM span's input attributes
        first_llm_input_value = None
        first_llm_input_mime = None
        first_llm_span = None

        for span in sorted_spans:
            if span.get('kind') == 'LLM':
                attrs = span.get('attributes', [])
                input_value = self._get_attribute(attrs, 'input.value')
                if input_value:
                    first_llm_input_value = input_value
                    first_llm_input_mime = self._get_attribute(attrs, 'input.mime_type') or 'application/json'
                    first_llm_span = span
                    break

        # Find last LLM span's output attributes
        last_llm_output_value = None
        last_llm_output_mime = None
        last_llm_span = None

        for span in reversed(sorted_spans):
            if span.get('kind') == 'LLM':
                attrs = span.get('attributes', [])
                output_value = self._get_attribute(attrs, 'output.value')
                if output_value:
                    last_llm_output_value = output_value
                    last_llm_output_mime = self._get_attribute(attrs, 'output.mime_type') or 'application/json'
                    last_llm_span = span
                    break

        # Bubble up input to all ancestors of first LLM span
        if first_llm_span and first_llm_input_value:
            current_span = first_llm_span
            while current_span:
                parent_span_id = current_span.get('parent_span_id')
                if parent_span_id is None:
                    # Reached root, add attributes here too
                    self._set_attribute(current_span['attributes'], 'input.value', first_llm_input_value)
                    self._set_attribute(current_span['attributes'], 'input.mime_type', first_llm_input_mime)
                    break

                parent_span = span_map.get(parent_span_id)
                if parent_span:
                    # Add input attributes to parent
                    self._set_attribute(parent_span['attributes'], 'input.value', first_llm_input_value)
                    self._set_attribute(parent_span['attributes'], 'input.mime_type', first_llm_input_mime)
                    current_span = parent_span
                else:
                    break

        # Bubble up output to all ancestors of last LLM span
        if last_llm_span and last_llm_output_value:
            current_span = last_llm_span
            while current_span:
                parent_span_id = current_span.get('parent_span_id')
                if parent_span_id is None:
                    # Reached root, add attributes here too
                    self._set_attribute(current_span['attributes'], 'output.value', last_llm_output_value)
                    self._set_attribute(current_span['attributes'], 'output.mime_type', last_llm_output_mime)
                    break

                parent_span = span_map.get(parent_span_id)
                if parent_span:
                    # Add output attributes to parent
                    self._set_attribute(parent_span['attributes'], 'output.value', last_llm_output_value)
                    self._set_attribute(parent_span['attributes'], 'output.mime_type', last_llm_output_mime)
                    current_span = parent_span
                else:
                    break

    def _determine_openinference_kind(self, span, attributes):
        """Determine the OpenInference span kind based on span characteristics"""
        span_name = span.name.lower() if span.name else ""

        # Check for LLM spans
        if (span.kind.name == 'LLM' or
            'gen_ai.system' in attributes or
            'gen_ai.request.model' in attributes or
            'llm.model_name' in attributes or
            'llm' in span_name):
            return 'LLM'

        # Check for tool/function call spans (ADK uses gen_ai.operation.name == 'execute_tool')
        if (span.kind.name == 'TOOL' or
            attributes.get('gen_ai.operation.name') == 'execute_tool' or
            'tool.name' in attributes or
            'gen_ai.tool.name' in attributes or
            'function.name' in attributes or
            'gen_ai.request.tool_calls' in attributes or
            'tool_call' in span_name or
            'tool' in span_name):
            return 'TOOL'

        # Check for agent spans
        if ('agent' in span_name or
            'gcp.vertex.agent' in str(attributes.keys()) or
            attributes.get('gen_ai.operation.name') == 'agent'):
            return 'AGENT'

        # Check for retriever spans
        if ('retriev' in span_name or
            'search' in span_name or
            'query' in span_name and 'vector' in span_name):
            return 'RETRIEVER'

        # Check for embedding spans
        if ('embed' in span_name or
            'embedding' in span_name):
            return 'EMBEDDING'

        # Check for reranker spans
        if ('rerank' in span_name):
            return 'RERANKER'

        # Default to CHAIN for other spans (sequences of operations)
        return 'CHAIN'

    def _unroll_messages(self, messages, prefix):
        """Unroll message array into flat attributes with indexed keys"""
        unrolled = {}

        for idx, msg in enumerate(messages):
            if not isinstance(msg, dict):
                continue

            # Add message.role and message.content
            if 'message.role' in msg:
                unrolled[f"{prefix}.{idx}.message.role"] = msg['message.role']

            if 'message.content' in msg:
                unrolled[f"{prefix}.{idx}.message.content"] = msg['message.content']

            # Check for tool_calls in the message
            if 'message.tool_calls' in msg:
                tool_calls = msg['message.tool_calls']
                if isinstance(tool_calls, list):
                    for tool_idx, tool_call in enumerate(tool_calls):
                        if isinstance(tool_call, dict):
                            # Add tool_call fields
                            if 'tool_call.id' in tool_call:
                                unrolled[f"{prefix}.{idx}.message.tool_calls.{tool_idx}.tool_call.id"] = tool_call['tool_call.id']

                            if 'tool_call.function' in tool_call:
                                func = tool_call['tool_call.function']
                                if isinstance(func, dict):
                                    if 'name' in func:
                                        unrolled[f"{prefix}.{idx}.message.tool_calls.{tool_idx}.tool_call.function.name"] = func['name']
                                    if 'arguments' in func:
                                        unrolled[f"{prefix}.{idx}.message.tool_calls.{tool_idx}.tool_call.function.arguments"] = func['arguments']

        return unrolled

    def _extract_openinference_attributes(self, span, attributes, span_kind):
        """Extract OpenInference-specific attributes based on span kind and data"""
        oi_attrs = {}

        # Extract input/output for all spans
        # Check for input in various locations
        if 'gcp.vertex.agent.llm_request' in attributes:
            llm_request = attributes['gcp.vertex.agent.llm_request']
            if isinstance(llm_request, str):
                try:
                    llm_request = json.loads(llm_request)
                except (json.JSONDecodeError, ValueError):
                    pass

            if isinstance(llm_request, dict) and llm_request:
                # For LLM spans, store the full request as input
                oi_attrs['input.value'] = json.dumps(llm_request)
                oi_attrs['input.mime_type'] = 'application/json'

                # Extract user message for simpler input representation
                if 'contents' in llm_request and isinstance(llm_request['contents'], list):
                    for content in llm_request['contents']:
                        if isinstance(content, dict) and content.get('role') == 'user':
                            parts = content.get('parts', [])
                            if parts and isinstance(parts, list):
                                for part in parts:
                                    if isinstance(part, dict) and 'text' in part:
                                        # Wrap text input in JSON object
                                        oi_attrs['input.value'] = json.dumps({"input": part['text']})
                                        oi_attrs['input.mime_type'] = 'application/json'
                                        break

        # Extract output
        if 'gcp.vertex.agent.llm_response' in attributes:
            llm_response = attributes['gcp.vertex.agent.llm_response']
            if isinstance(llm_response, str):
                try:
                    llm_response = json.loads(llm_response)
                except (json.JSONDecodeError, ValueError):
                    # Wrap text output in JSON object
                    oi_attrs['output.value'] = json.dumps({"output": llm_response})
                    oi_attrs['output.mime_type'] = 'application/json'

            if isinstance(llm_response, dict):
                # Try to extract text output from response
                text_output = ""  # Default to empty string

                if 'content' in llm_response and isinstance(llm_response['content'], dict):
                    content = llm_response['content']
                    if 'parts' in content and isinstance(content['parts'], list):
                        text_parts = []
                        for part in content['parts']:
                            if isinstance(part, dict) and 'text' in part:
                                text_parts.append(part['text'])
                        if text_parts:
                            text_output = ' '.join(text_parts)
                        # else: text_output stays as ""
                    # else: Content exists but no parts field, text_output stays as ""
                # else: No content field, text_output stays as ""

                # Always wrap the extracted text (even if empty)
                oi_attrs['output.value'] = json.dumps({"output": text_output})
                oi_attrs['output.mime_type'] = 'application/json'

        # Check for tool response (for TOOL spans)
        if 'gcp.vertex.agent.tool_response' in attributes:
            tool_response = attributes['gcp.vertex.agent.tool_response']
            if isinstance(tool_response, str):
                try:
                    tool_response_obj = json.loads(tool_response)
                    oi_attrs['output.value'] = json.dumps(tool_response_obj)
                    oi_attrs['output.mime_type'] = 'application/json'
                except (json.JSONDecodeError, ValueError):
                    # Wrap text output in JSON object
                    oi_attrs['output.value'] = json.dumps({"output": tool_response})
                    oi_attrs['output.mime_type'] = 'application/json'

        # Check for tool parameters (for TOOL spans)
        if 'gcp.vertex.agent.tool_parameters' in attributes:
            tool_params = attributes['gcp.vertex.agent.tool_parameters']
            if isinstance(tool_params, str):
                try:
                    tool_params_obj = json.loads(tool_params)
                    oi_attrs['input.value'] = json.dumps(tool_params_obj)
                    oi_attrs['input.mime_type'] = 'application/json'
                except (json.JSONDecodeError, ValueError):
                    # Wrap text input in JSON object
                    oi_attrs['input.value'] = json.dumps({"input": tool_params})
                    oi_attrs['input.mime_type'] = 'application/json'

        # LLM-specific attributes
        if span_kind == 'LLM':
            # Model name
            model_name = (
                attributes.get('gen_ai.request.model') or
                attributes.get('gen_ai.response.model') or
                attributes.get('llm.model_name') or
                attributes.get('gen_ai.system')
            )
            if model_name:
                oi_attrs['llm.model_name'] = model_name

            # Token counts
            prompt_tokens = None
            completion_tokens = None
            total_tokens = None

            if 'gen_ai.usage.input_tokens' in attributes:
                prompt_tokens = attributes['gen_ai.usage.input_tokens']
                oi_attrs['llm.token_count.prompt'] = prompt_tokens

            if 'gen_ai.usage.output_tokens' in attributes:
                completion_tokens = attributes['gen_ai.usage.output_tokens']
                oi_attrs['llm.token_count.completion'] = completion_tokens

            if 'gen_ai.usage.total_tokens' in attributes:
                total_tokens = attributes['gen_ai.usage.total_tokens']
                oi_attrs['llm.token_count.total'] = total_tokens

            # If total not provided but we have prompt and completion, calculate it
            if not total_tokens and prompt_tokens is not None and completion_tokens is not None:
                try:
                    prompt_int = int(float(prompt_tokens)) if isinstance(prompt_tokens, str) else int(prompt_tokens)
                    completion_int = int(float(completion_tokens)) if isinstance(completion_tokens, str) else int(completion_tokens)
                    oi_attrs['llm.token_count.total'] = str(prompt_int + completion_int)
                except (ValueError, TypeError):
                    pass

            # Input messages (for chat APIs)
            if 'gcp.vertex.agent.llm_request' in attributes:
                llm_request = attributes['gcp.vertex.agent.llm_request']
                if isinstance(llm_request, str):
                    try:
                        llm_request = json.loads(llm_request)
                    except (json.JSONDecodeError, ValueError):
                        pass

                if isinstance(llm_request, dict) and 'contents' in llm_request:
                    # Transform to OpenInference format and unroll
                    input_messages = []
                    for content in llm_request['contents']:
                        if isinstance(content, dict):
                            role = content.get('role', 'user')
                            parts = content.get('parts', [])

                            # Serialize parts as JSON for message.content
                            if parts:
                                content_str = json.dumps(parts)
                            else:
                                content_str = ""

                            input_messages.append({
                                "message.role": role,
                                "message.content": content_str
                            })

                    if input_messages:
                        # Unroll messages into flat attributes
                        unrolled = self._unroll_messages(input_messages, 'llm.input_messages')
                        oi_attrs.update(unrolled)

            # Output messages (for chat APIs)
            if 'gcp.vertex.agent.llm_response' in attributes:
                llm_response = attributes['gcp.vertex.agent.llm_response']
                if isinstance(llm_response, str):
                    try:
                        llm_response = json.loads(llm_response)
                    except (json.JSONDecodeError, ValueError):
                        pass

                if isinstance(llm_response, dict) and 'content' in llm_response:
                    # Transform to OpenInference format and unroll
                    content = llm_response['content']
                    if isinstance(content, dict):
                        role = content.get('role', 'assistant')
                        parts = content.get('parts', [])

                        # Serialize parts as JSON for message.content
                        if parts:
                            content_str = json.dumps(parts)
                        else:
                            content_str = ""

                        message = {
                            "message.role": role,
                            "message.content": content_str
                        }

                        # Extract tool_calls from function_call in parts
                        tool_calls = []
                        if isinstance(parts, list):
                            for part in parts:
                                if isinstance(part, dict) and 'function_call' in part:
                                    fc = part['function_call']
                                    if isinstance(fc, dict):
                                        tool_call = {
                                            "tool_call.function": {
                                                "name": fc.get('name', ''),
                                                "arguments": json.dumps(fc.get('args', {}))
                                            }
                                        }
                                        # Add ID if present
                                        if 'id' in fc:
                                            tool_call['tool_call.id'] = fc['id']
                                        tool_calls.append(tool_call)

                        if tool_calls:
                            message['message.tool_calls'] = tool_calls

                        output_messages = [message]

                        # Unroll messages into flat attributes
                        unrolled = self._unroll_messages(output_messages, 'llm.output_messages')
                        oi_attrs.update(unrolled)

            # Invocation parameters
            invocation_params = {}
            param_keys = ['gen_ai.request.temperature', 'gen_ai.request.top_p',
                         'gen_ai.request.top_k', 'gen_ai.request.max_tokens']
            for key in param_keys:
                if key in attributes:
                    param_name = key.replace('gen_ai.request.', '')
                    invocation_params[param_name] = attributes[key]

            if invocation_params:
                oi_attrs['llm.invocation_parameters'] = json.dumps(invocation_params)

            # Function call - Extract from LLM response when present
            if 'gcp.vertex.agent.llm_response' in attributes:
                llm_response = attributes['gcp.vertex.agent.llm_response']
                if isinstance(llm_response, str):
                    try:
                        llm_response = json.loads(llm_response)
                    except (json.JSONDecodeError, ValueError):
                        llm_response = None

                if isinstance(llm_response, dict) and 'content' in llm_response:
                    content = llm_response['content']
                    if isinstance(content, dict) and 'parts' in content:
                        parts = content['parts']
                        if isinstance(parts, list):
                            # Extract function calls from parts
                            function_calls = []
                            for part in parts:
                                if isinstance(part, dict) and 'function_call' in part:
                                    fc = part['function_call']
                                    if isinstance(fc, dict):
                                        function_calls.append(fc)

                            if function_calls:
                                oi_attrs['llm.function_call'] = json.dumps(function_calls)

            # Prompts (for completions APIs, not chat)
            if 'gcp.vertex.agent.llm_request' in attributes:
                llm_request = attributes['gcp.vertex.agent.llm_request']
                if isinstance(llm_request, str):
                    try:
                        llm_request = json.loads(llm_request)
                    except (json.JSONDecodeError, ValueError):
                        llm_request = None

                # Check for 'prompt' field (completions API) vs 'contents' (chat API)
                if isinstance(llm_request, dict) and 'prompt' in llm_request:
                    prompts = llm_request['prompt']
                    if isinstance(prompts, list):
                        oi_attrs['llm.prompts'] = json.dumps(prompts)
                    elif isinstance(prompts, str):
                        oi_attrs['llm.prompts'] = json.dumps([prompts])

            # Prompt template attributes
            if 'llm.prompt_template.template' in attributes:
                oi_attrs['llm.prompt_template.template'] = attributes['llm.prompt_template.template']

            if 'llm.prompt_template.variables' in attributes:
                template_vars = attributes['llm.prompt_template.variables']
                if isinstance(template_vars, str):
                    oi_attrs['llm.prompt_template.variables'] = template_vars
                elif isinstance(template_vars, (list, dict)):
                    oi_attrs['llm.prompt_template.variables'] = json.dumps(template_vars)

            if 'llm.prompt_template.version' in attributes:
                oi_attrs['llm.prompt_template.version'] = attributes['llm.prompt_template.version']

        # TOOL-specific attributes
        if span_kind == 'TOOL':
            # Tool name - extract from various locations
            tool_name = (
                attributes.get('gen_ai.tool.name') or
                attributes.get('tool.name') or
                attributes.get('function.name')
            )

            # If not found in attributes, try to extract from span name
            if not tool_name:
                # ADK formats span names as "execute_tool <tool_name>"
                if span.name.startswith('execute_tool '):
                    tool_name = span.name.replace('execute_tool ', '').strip()
                else:
                    tool_name = span.name

            if tool_name:
                oi_attrs['tool.name'] = tool_name

            # Tool description - check multiple possible attribute names
            tool_description = (
                attributes.get('gen_ai.tool.description') or
                attributes.get('tool.description') or
                attributes.get('function.description')
            )
            if tool_description:
                oi_attrs['tool.description'] = tool_description

            # Tool parameters - Extract from tool span's own attributes
            tool_params = None

            # Check the tool span itself for gcp.vertex.agent.tool_call_args
            if 'gcp.vertex.agent.tool_call_args' in attributes:
                tool_call_args_str = attributes['gcp.vertex.agent.tool_call_args']
                if tool_call_args_str:
                    try:
                        tool_params = json.loads(tool_call_args_str)
                    except (json.JSONDecodeError, ValueError):
                        pass

            # Fallback: Check other tool-specific attributes
            if not tool_params:
                tool_param_keys = [
                    'gcp.vertex.agent.tool_parameters',
                    'gen_ai.tool.parameters',
                    'function.arguments',
                    'tool.arguments',
                    'tool.parameters'
                ]
                for key in tool_param_keys:
                    if key in attributes:
                        tool_params = attributes[key]
                        break

            if tool_params:
                # Ensure it's a JSON string for tool.parameters
                if isinstance(tool_params, str):
                    # Verify it's valid JSON
                    try:
                        json.loads(tool_params)
                        oi_attrs['tool.parameters'] = tool_params
                        oi_attrs['input.value'] = tool_params  # Same as tool.parameters
                        oi_attrs['input.mime_type'] = 'application/json'
                    except (json.JSONDecodeError, ValueError):
                        # If not valid JSON, wrap it
                        params_json = json.dumps({"value": tool_params})
                        oi_attrs['tool.parameters'] = params_json
                        oi_attrs['input.value'] = params_json  # Same as tool.parameters
                        oi_attrs['input.mime_type'] = 'application/json'
                else:
                    # Convert to JSON string
                    params_json = json.dumps(tool_params)
                    oi_attrs['tool.parameters'] = params_json
                    oi_attrs['input.value'] = params_json  # Same as tool.parameters
                    oi_attrs['input.mime_type'] = 'application/json'

        # Session and User IDs
        session_id_keys = ['session.id', 'session_id', 'ai.session.id',
                          'app.session.id', 'user.session.id', 'gcp.vertex.agent.session_id']
        for key in session_id_keys:
            if key in attributes:
                oi_attrs['session.id'] = attributes[key]
                break

        user_id_keys = ['user.id', 'user_id']
        for key in user_id_keys:
            if key in attributes:
                oi_attrs['user.id'] = attributes[key]
                break

        # Metadata (preserve any metadata attributes)
        if 'metadata' in attributes:
            oi_attrs['metadata'] = attributes['metadata']

        # Tags
        if 'tags' in attributes or 'tag.tags' in attributes:
            oi_attrs['tag.tags'] = attributes.get('tag.tags', attributes.get('tags'))

        return oi_attrs

    def _format_timestamp(self, timestamp_ns):
        """Convert nanosecond timestamp to ISO 8601 format with timezone"""
        if not timestamp_ns:
            return None
        # OpenTelemetry timestamps are in nanoseconds since epoch
        timestamp_seconds = timestamp_ns / 1_000_000_000
        dt = datetime.fromtimestamp(timestamp_seconds)
        # Format as ISO 8601 with timezone (UTC)
        return dt.isoformat() + 'Z'

    def _convert_attributes_to_string_map(self, attributes):
        """Convert all attribute values to strings with JSON encoding"""
        string_map = {}
        for key, value in attributes.items():
            if isinstance(value, str):
                # JSON-encode string values to add outer quotes and escape special chars
                string_map[key] = json.dumps(value)
            elif isinstance(value, (list, dict)):
                string_map[key] = json.dumps(value)
            elif value is None:
                string_map[key] = ""
            else:
                string_map[key] = str(value)
        return string_map

    def _dict_to_key_value_list(self, attr_dict):
        """Convert a dictionary to a list of key-value maps"""
        if not attr_dict:
            return []
        return [{"key": k, "value": v} for k, v in attr_dict.items()]

    def _get_attribute(self, attributes_list, key):
        """Get an attribute value from a list of key-value maps"""
        if not attributes_list:
            return None
        for attr in attributes_list:
            if attr.get("key") == key:
                return attr.get("value")
        return None

    def _set_attribute(self, attributes_list, key, value):
        """Set or update an attribute in a list of key-value maps"""
        # Find existing attribute
        for attr in attributes_list:
            if attr.get("key") == key:
                attr["value"] = value
                return
        # Add new attribute if not found
        attributes_list.append({"key": key, "value": value})

    def _key_value_list_to_dict(self, attributes_list):
        """Convert a list of key-value maps back to a dictionary"""
        if not attributes_list:
            return {}
        return {attr["key"]: attr["value"] for attr in attributes_list if "key" in attr and "value" in attr}

    def _transform_attributes(self, attributes):
        """Transform attributes to OpenInference semantic conventions"""
        oi_attributes = {}

        # Map common LLM attributes to OpenInference format
        attribute_mapping = {
            "gen_ai.system": "llm.system",
            "gen_ai.request.model": "llm.model_name",
            "gen_ai.response.model": "llm.model_name",
            "gen_ai.usage.input_tokens": "llm.token_count.prompt",
            "gen_ai.usage.output_tokens": "llm.token_count.completion",
            "gen_ai.usage.total_tokens": "llm.token_count.total",
        }

        for key, value in attributes.items():
            if key in attribute_mapping:
                oi_attributes[attribute_mapping[key]] = value
            else:
                oi_attributes[key] = value

        return oi_attributes

    def _extract_input(self, root_span, trace_spans):
        """Extract the input from the root span or child spans"""
        if not root_span:
            return ""

        # First check root span attributes (now OpenInference format)
        attributes = self._key_value_list_to_dict(root_span.get('attributes', []))

        # Check for OpenInference input.value first (already extracted)
        if 'input.value' in attributes and attributes['input.value']:
            return attributes['input.value']

        # Try various common attribute names for input in root span
        input_keys = [
            'input.value',
            'input',
            'gen_ai.prompt',
            'llm.prompt',
            'user.message',
            'query',
            'request',
            'user_input',
            'prompt',
        ]

        for key in input_keys:
            if key in attributes:
                value = attributes[key]
                if isinstance(value, str):
                    return value
                elif isinstance(value, (list, dict)):
                    return json.dumps(value)
                else:
                    return str(value)

        # Check events in root span
        events = root_span.get('events', [])
        for event in events:
            event_name = event.get('name', '').lower()
            if 'input' in event_name or 'prompt' in event_name or 'user' in event_name:
                event_attrs = event.get('attributes', {})
                if 'input.value' in event_attrs:
                    return str(event_attrs['input.value'])
                if 'input' in event_attrs:
                    return str(event_attrs['input'])

        # If not found in root span, search for the first LLM span's input (user query)
        # Sort spans by start_time to get chronological order
        sorted_spans = sorted(trace_spans, key=lambda s: s.get('start_time', ''))

        for span in sorted_spans:
            span_attrs = self._key_value_list_to_dict(span.get('attributes', []))
            span_kind = span.get('kind')

            # Only look at LLM spans for the trace-level input
            if span_kind == 'LLM' and 'input.value' in span_attrs and span_attrs['input.value']:
                input_val = span_attrs['input.value']
                mime_type = span_attrs.get('input.mime_type', 'application/json')

                # Unwrap {"input": value} format if present
                if mime_type == 'application/json':
                    try:
                        parsed = json.loads(input_val)
                        if isinstance(parsed, dict) and 'input' in parsed and len(parsed) == 1:
                            return parsed['input']
                    except (json.JSONDecodeError, ValueError):
                        pass

                return input_val

        # Fallback: if no LLM span found, look at all spans
        for span in sorted_spans:
            span_attrs = self._key_value_list_to_dict(span.get('attributes', []))

            if 'input.value' in span_attrs and span_attrs['input.value']:
                input_val = span_attrs['input.value']
                mime_type = span_attrs.get('input.mime_type', 'application/json')

                # Unwrap {"input": value} format if present
                if mime_type == 'application/json':
                    try:
                        parsed = json.loads(input_val)
                        if isinstance(parsed, dict) and 'input' in parsed and len(parsed) == 1:
                            return parsed['input']
                    except (json.JSONDecodeError, ValueError):
                        pass

                return input_val

            # Check for GCP Vertex Agent LLM request (ADK-specific) as fallback
            if 'gcp.vertex.agent.llm_request' in span_attrs:
                llm_request = span_attrs['gcp.vertex.agent.llm_request']

                # Parse JSON string if needed
                if isinstance(llm_request, str):
                    try:
                        llm_request = json.loads(llm_request)
                    except (json.JSONDecodeError, ValueError):
                        continue

                if isinstance(llm_request, dict) and llm_request:  # Make sure it's not empty
                    # Check for contents array (Gemini API format)
                    if 'contents' in llm_request and isinstance(llm_request['contents'], list):
                        for content in llm_request['contents']:
                            if isinstance(content, dict) and content.get('role') == 'user':
                                parts = content.get('parts', [])
                                if parts and isinstance(parts, list):
                                    for part in parts:
                                        if isinstance(part, dict) and 'text' in part:
                                            return part['text']
                    # Check for messages array
                    if 'messages' in llm_request and isinstance(llm_request['messages'], list):
                        for msg in llm_request['messages']:
                            if isinstance(msg, dict) and msg.get('role') == 'user':
                                return msg.get('content', '')

            # Check for gen_ai prompt-related attributes
            if 'gen_ai.prompt' in span_attrs:
                return str(span_attrs['gen_ai.prompt'])

            # Check for messages array (common in LLM APIs)
            for key in ['gen_ai.request.messages', 'llm.messages', 'messages']:
                if key in span_attrs:
                    messages = span_attrs[key]
                    if isinstance(messages, list) and len(messages) > 0:
                        # Get the first user message
                        for msg in messages:
                            if isinstance(msg, dict):
                                if msg.get('role') == 'user':
                                    content = msg.get('content', msg.get('parts', ''))
                                    if content:
                                        return str(content) if isinstance(content, str) else json.dumps(content)
                        # If no user message, return first message
                        first_msg = messages[0]
                        if isinstance(first_msg, dict):
                            content = first_msg.get('content', first_msg.get('parts', ''))
                            return str(content) if isinstance(content, str) else json.dumps(content)

            # Check events in all spans
            for event in span.get('events', []):
                event_name = event.get('name', '').lower()
                if 'input' in event_name or 'prompt' in event_name or 'user' in event_name:
                    event_attrs = event.get('attributes', {})
                    if 'input.value' in event_attrs:
                        return str(event_attrs['input.value'])
                    if 'input' in event_attrs:
                        return str(event_attrs['input'])

        # Default to empty string if no input found
        return ""

    def _extract_output(self, root_span, trace_spans):
        """Extract the output from the root span or child spans"""
        if not root_span:
            return ""

        # First check root span attributes (now OpenInference format)
        attributes = self._key_value_list_to_dict(root_span.get('attributes', []))

        # Check for OpenInference output.value first (already extracted)
        if 'output.value' in attributes and attributes['output.value']:
            return attributes['output.value']

        # Try various common attribute names for output
        output_keys = [
            'output.value',
            'output',
            'gen_ai.response',
            'llm.response',
            'response',
            'result',
            'answer',
            'completion',
        ]

        for key in output_keys:
            if key in attributes:
                value = attributes[key]
                if isinstance(value, str):
                    return value
                elif isinstance(value, (list, dict)):
                    return json.dumps(value)
                else:
                    return str(value)

        # Check events in root span
        events = root_span.get('events', [])
        for event in events:
            event_name = event.get('name', '').lower()
            if 'output' in event_name or 'response' in event_name or 'completion' in event_name:
                event_attrs = event.get('attributes', {})
                if 'output.value' in event_attrs:
                    return str(event_attrs['output.value'])
                elif 'response' in event_attrs:
                    return str(event_attrs['response'])

        # If not found in root span, search for the last LLM span's output (final answer)
        # Sort spans by start_time and search in reverse to get the last LLM output
        sorted_spans = sorted(trace_spans, key=lambda s: s.get('start_time', ''))

        # First priority: Find the last LLM span (the actual agent response to user)
        last_llm_span = None
        for span in reversed(sorted_spans):
            if span.get('kind') == 'LLM':
                last_llm_span = span
                break

        # If we found the last LLM span and it has output.value, use it (even if empty string)
        if last_llm_span:
            span_attrs = self._key_value_list_to_dict(last_llm_span.get('attributes', []))
            if 'output.value' in span_attrs:
                output_val = span_attrs['output.value']
                mime_type = span_attrs.get('output.mime_type', 'application/json')

                # Unwrap {"output": value} format if present
                if mime_type == 'application/json' and output_val:  # Only unwrap if not empty
                    try:
                        parsed = json.loads(output_val)
                        if isinstance(parsed, dict) and 'output' in parsed and len(parsed) == 1:
                            return parsed['output']
                    except (json.JSONDecodeError, ValueError):
                        pass

                return output_val

        # Fallback: if last LLM span had no output.value, look for earlier LLM spans with output
        for span in reversed(sorted_spans):
            span_attrs = self._key_value_list_to_dict(span.get('attributes', []))
            span_kind = span.get('kind')

            if span_kind == 'LLM' and 'output.value' in span_attrs and span_attrs['output.value']:
                output_val = span_attrs['output.value']
                mime_type = span_attrs.get('output.mime_type', 'application/json')

                # Unwrap {"output": value} format if present
                if mime_type == 'application/json':
                    try:
                        parsed = json.loads(output_val)
                        if isinstance(parsed, dict) and 'output' in parsed and len(parsed) == 1:
                            return parsed['output']
                    except (json.JSONDecodeError, ValueError):
                        pass

                return output_val

        # Final fallback: if no LLM spans found with output, look at all other spans in reverse order
        for span in reversed(sorted_spans):
            span_attrs = self._key_value_list_to_dict(span.get('attributes', []))

            if 'output.value' in span_attrs and span_attrs['output.value']:
                output_val = span_attrs['output.value']
                mime_type = span_attrs.get('output.mime_type', 'application/json')

                # Unwrap {"output": value} format if present
                if mime_type == 'application/json':
                    try:
                        parsed = json.loads(output_val)
                        if isinstance(parsed, dict) and 'output' in parsed and len(parsed) == 1:
                            return parsed['output']
                    except (json.JSONDecodeError, ValueError):
                        pass

                return output_val

            # Check for GCP Vertex Agent LLM response (ADK-specific) as fallback
            if 'gcp.vertex.agent.llm_response' in span_attrs:
                llm_response = span_attrs['gcp.vertex.agent.llm_response']

                # Parse JSON string if needed
                if isinstance(llm_response, str):
                    try:
                        llm_response = json.loads(llm_response)
                    except (json.JSONDecodeError, ValueError):
                        # If it can't be parsed, it might be the raw string response
                        return llm_response

                if isinstance(llm_response, dict):
                    # Check for content.parts (ADK format from Gemini)
                    if 'content' in llm_response and isinstance(llm_response['content'], dict):
                        content = llm_response['content']
                        if 'parts' in content and isinstance(content['parts'], list):
                            text_parts = []
                            for part in content['parts']:
                                if isinstance(part, dict) and 'text' in part:
                                    text_parts.append(part['text'])
                            if text_parts:
                                return ' '.join(text_parts)

                    # Check for candidates array (Gemini API format)
                    if 'candidates' in llm_response and isinstance(llm_response['candidates'], list):
                        if llm_response['candidates']:
                            candidate = llm_response['candidates'][0]
                            if isinstance(candidate, dict):
                                content = candidate.get('content', {})
                                if isinstance(content, dict):
                                    parts = content.get('parts', [])
                                    if parts and isinstance(parts, list):
                                        # Collect all text parts
                                        text_parts = []
                                        for part in parts:
                                            if isinstance(part, dict) and 'text' in part:
                                                text_parts.append(part['text'])
                                        if text_parts:
                                            return ' '.join(text_parts)

            # Check for gen_ai response-related attributes
            for key in ['gen_ai.completion', 'gen_ai.response.text', 'llm.response']:
                if key in span_attrs:
                    return str(span_attrs[key])

            # Check events in all spans
            for event in span.get('events', []):
                event_name = event.get('name', '').lower()
                if 'output' in event_name or 'response' in event_name or 'completion' in event_name:
                    event_attrs = event.get('attributes', {})
                    if 'output.value' in event_attrs:
                        return str(event_attrs['output.value'])
                    elif 'response' in event_attrs:
                        return str(event_attrs['response'])

        # Default to empty string if no output found
        return ""

    def _extract_timestamp(self, root_span):
        """Extract the timestamp from the root span's start_time"""
        if not root_span:
            return None

        start_time = root_span.get('start_time')
        if start_time:
            # If already a string (ISO 8601), return as-is
            if isinstance(start_time, str):
                return start_time
            # Otherwise convert from nanoseconds to ISO 8601 format
            timestamp_seconds = start_time / 1_000_000_000
            dt = datetime.fromtimestamp(timestamp_seconds)
            return dt.isoformat() + 'Z'

        return None

    def _extract_duration_ms(self, root_span):
        """Extract the duration in milliseconds from the root span"""
        if not root_span:
            return None

        start_time = root_span.get('start_time')
        end_time = root_span.get('end_time')

        if start_time and end_time:
            # If timestamps are ISO 8601 strings, parse them
            if isinstance(start_time, str) and isinstance(end_time, str):
                # Remove 'Z' and parse ISO 8601 format
                start_dt = datetime.fromisoformat(start_time.rstrip('Z'))
                end_dt = datetime.fromisoformat(end_time.rstrip('Z'))
                duration_seconds = (end_dt - start_dt).total_seconds()
                return int(duration_seconds * 1000)
            # Otherwise convert from nanoseconds
            duration_ns = end_time - start_time
            duration_ms = int(duration_ns / 1_000_000)
            return duration_ms

        return None

    def _extract_total_token_count(self, trace_spans):
        """Extract the total token count from all spans in the trace"""
        total_tokens = 0

        # Token attribute keys to look for
        total_token_keys = [
            'gen_ai.usage.total_tokens',
            'llm.token_count.total',
            'token_count.total',
        ]

        input_token_keys = [
            'gen_ai.usage.input_tokens',
            'llm.token_count.prompt',
            'token_count.prompt',
        ]

        output_token_keys = [
            'gen_ai.usage.output_tokens',
            'llm.token_count.completion',
            'token_count.completion',
        ]

        for span in trace_spans:
            attributes = self._key_value_list_to_dict(span.get('attributes', []))
            span_tokens = 0

            # First try to get total tokens directly
            for key in total_token_keys:
                if key in attributes:
                    value = attributes[key]
                    try:
                        span_tokens = int(float(value))
                        break
                    except (ValueError, TypeError):
                        continue

            # If no total found, try to sum input + output tokens
            if span_tokens == 0:
                input_tokens = 0
                output_tokens = 0

                for key in input_token_keys:
                    if key in attributes:
                        value = attributes[key]
                        try:
                            input_tokens = int(float(value))
                            break
                        except (ValueError, TypeError):
                            continue

                for key in output_token_keys:
                    if key in attributes:
                        value = attributes[key]
                        try:
                            output_tokens = int(float(value))
                            break
                        except (ValueError, TypeError):
                            continue

                span_tokens = input_tokens + output_tokens

            total_tokens += span_tokens

        return total_tokens

    def _extract_prompt_token_count(self, trace_spans):
        """Extract the total prompt/input token count from all spans in the trace"""
        prompt_tokens = 0

        input_token_keys = [
            'gen_ai.usage.input_tokens',
            'llm.token_count.prompt',
            'token_count.prompt',
            'prompt_tokens',
        ]

        for span in trace_spans:
            attributes = self._key_value_list_to_dict(span.get('attributes', []))

            for key in input_token_keys:
                if key in attributes:
                    value = attributes[key]
                    try:
                        prompt_tokens += int(float(value))
                        break
                    except (ValueError, TypeError):
                        continue

        return prompt_tokens

    def _extract_completion_token_count(self, trace_spans):
        """Extract the total completion/output token count from all spans in the trace"""
        completion_tokens = 0

        output_token_keys = [
            'gen_ai.usage.output_tokens',
            'llm.token_count.completion',
            'token_count.completion',
            'completion_tokens',
        ]

        for span in trace_spans:
            attributes = self._key_value_list_to_dict(span.get('attributes', []))

            for key in output_token_keys:
                if key in attributes:
                    value = attributes[key]
                    try:
                        completion_tokens += int(float(value))
                        break
                    except (ValueError, TypeError):
                        continue

        return completion_tokens

    def _extract_tool_metrics(self, trace_spans):
        """Extract tool call metrics from all spans in the trace"""
        tool_call_count = 0
        tool_call_error_count = 0
        tool_call_name_counts = {}

        for span in trace_spans:
            attributes = self._key_value_list_to_dict(span.get('attributes', []))
            span_kind = span.get('kind', '')

            # Identify tool call spans (ADK uses gen_ai.operation.name == 'execute_tool')
            is_tool_call = (
                span_kind == 'TOOL' or
                attributes.get('gen_ai.operation.name') == 'execute_tool' or
                'tool.name' in attributes or
                'gen_ai.tool.name' in attributes or
                'function.name' in attributes or
                'gen_ai.request.tool_calls' in attributes or
                'tool_call' in span.get('name', '').lower()
            )

            if is_tool_call:
                tool_call_count += 1

                # Check for errors
                status = span.get('status', {})
                status_code = status.get('code', 'UNSET')
                if status_code == 'ERROR':
                    tool_call_error_count += 1

                # Extract tool name (ADK uses gen_ai.tool.name)
                tool_name = (
                    attributes.get('gen_ai.tool.name') or
                    attributes.get('tool.name') or
                    attributes.get('function.name') or
                    attributes.get('gen_ai.tool.name') or
                    span.get('name', 'unknown')
                )

                # Count tool names
                if tool_name:
                    tool_call_name_counts[tool_name] = tool_call_name_counts.get(tool_name, 0) + 1

        return {
            "tool_call_count": tool_call_count,
            "tool_call_error_count": tool_call_error_count,
            "tool_call_name_counts": tool_call_name_counts,
        }

    def _extract_llm_metrics(self, trace_spans):
        """Extract LLM call metrics from all spans in the trace"""
        llm_call_count = 0
        llm_call_error_count = 0
        llm_call_model_counts = {}

        for span in trace_spans:
            attributes = self._key_value_list_to_dict(span.get('attributes', []))
            span_kind = span.get('kind', '')

            # Identify LLM call spans
            is_llm_call = (
                span_kind == 'LLM' or
                'gen_ai.system' in attributes or
                'gen_ai.request.model' in attributes or
                'llm.model_name' in attributes or
                'llm' in span.get('name', '').lower()
            )

            if is_llm_call:
                llm_call_count += 1

                # Check for errors
                status = span.get('status', {})
                status_code = status.get('code', 'UNSET')
                if status_code == 'ERROR':
                    llm_call_error_count += 1

                # Extract model name
                model_name = (
                    attributes.get('gen_ai.request.model') or
                    attributes.get('gen_ai.response.model') or
                    attributes.get('llm.model_name') or
                    attributes.get('gen_ai.system')
                )

                # Count model names
                if model_name:
                    llm_call_model_counts[model_name] = llm_call_model_counts.get(model_name, 0) + 1

        return {
            "llm_call_count": llm_call_count,
            "llm_call_error_count": llm_call_error_count,
            "llm_call_model_counts": llm_call_model_counts,
        }

    def _extract_call_sequence(self, trace_spans):
        """Extract the sequence of tool and LLM calls from the trace"""
        calls = []

        for span in trace_spans:
            attributes = self._key_value_list_to_dict(span.get('attributes', []))
            span_kind = span.get('kind', '')
            start_time = span.get('start_time')

            # Check if this is a tool call (ADK uses gen_ai.operation.name == 'execute_tool')
            is_tool_call = (
                span_kind == 'TOOL' or
                attributes.get('gen_ai.operation.name') == 'execute_tool' or
                'tool.name' in attributes or
                'gen_ai.tool.name' in attributes or
                'function.name' in attributes or
                'gen_ai.request.tool_calls' in attributes or
                'tool_call' in span.get('name', '').lower()
            )

            # Check if this is an LLM call
            is_llm_call = (
                span_kind == 'LLM' or
                'gen_ai.system' in attributes or
                'gen_ai.request.model' in attributes or
                'llm.model_name' in attributes or
                'llm' in span.get('name', '').lower()
            )

            if is_tool_call:
                tool_name = (
                    attributes.get('gen_ai.tool.name') or
                    attributes.get('tool.name') or
                    attributes.get('function.name') or
                    span.get('name', 'unknown')
                )
                calls.append({
                    'type': 'tool',
                    'name': tool_name,
                    'start_time': start_time,
                    'label': f"tool:{tool_name}"
                })
            elif is_llm_call:
                model_name = (
                    attributes.get('gen_ai.request.model') or
                    attributes.get('gen_ai.response.model') or
                    attributes.get('llm.model_name') or
                    attributes.get('gen_ai.system') or
                    'unknown'
                )
                calls.append({
                    'type': 'llm',
                    'name': model_name,
                    'start_time': start_time,
                    'label': f"llm:{model_name}"
                })

        # Sort by start_time to get the chronological sequence
        # Note: start_time is now ISO 8601 string, but should still sort correctly
        calls.sort(key=lambda x: x['start_time'] if x['start_time'] else "")

        # Extract just the labels for the sequence
        sequence = [call['label'] for call in calls]

        return sequence

    def _extract_trace_status(self, trace_spans):
        """Extract the overall trace status from all spans"""
        # Check all spans for errors
        error_spans = []
        has_success = False

        for span in trace_spans:
            status = span.get('status', {})
            status_code = status.get('code', 'UNSET')

            if status_code == 'ERROR':
                span_name = span.get('name', 'unknown')
                status_message = status.get('message', '')
                error_spans.append({
                    'name': span_name,
                    'message': status_message
                })
            elif status_code == 'OK':
                has_success = True

        # If any span has an error, trace status is ERROR
        if error_spans:
            # Build error message listing all failed operations
            error_messages = []
            for error_span in error_spans:
                if error_span['message']:
                    error_messages.append(f"{error_span['name']}: {error_span['message']}")
                else:
                    error_messages.append(f"{error_span['name']} failed")

            return {
                "status": "ERROR",
                "status_message": "; ".join(error_messages)
            }

        # If all spans are successful or unset
        return {
            "status": "OK" if has_success else "UNSET",
            "status_message": ""
        }

    def _extract_session_id(self, root_span, trace_spans):
        """Extract the session ID from the root span or child spans"""
        if not root_span:
            return ""

        # First check root span attributes
        attributes = self._key_value_list_to_dict(root_span.get('attributes', []))

        # Try various common attribute names for session ID
        session_id_keys = [
            'session.id',
            'session_id',
            'ai.session.id',
            'app.session.id',
            'user.session.id',
            'gcp.vertex.agent.session_id',
        ]

        for key in session_id_keys:
            if key in attributes:
                value = attributes[key]
                if value:
                    return str(value)

        # If not found in root span, search all spans
        for span in trace_spans:
            span_attrs = self._key_value_list_to_dict(span.get('attributes', []))
            for key in session_id_keys:
                if key in span_attrs:
                    value = span_attrs[key]
                    if value:
                        return str(value)

        # Default to empty string if no session ID found
        return ""

    def _get_model_pricing(self, model_name):
        """Get pricing for a model, with fuzzy matching"""
        if not model_name:
            return None

        model_name_lower = model_name.lower()

        # Try exact match first
        if model_name_lower in MODEL_PRICING:
            return MODEL_PRICING[model_name_lower]

        # Try fuzzy matching - check if any pricing key is contained in the model name
        for pricing_key, pricing in MODEL_PRICING.items():
            if pricing_key in model_name_lower or model_name_lower in pricing_key:
                return pricing

        # No pricing found
        return None

    def _calculate_costs(self, trace_spans):
        """Calculate cost estimates based on token usage and models used"""
        total_prompt_cost = 0.0
        total_completion_cost = 0.0

        # Input/output token keys
        input_token_keys = [
            'gen_ai.usage.input_tokens',
            'llm.token_count.prompt',
            'token_count.prompt',
            'prompt_tokens',
        ]

        output_token_keys = [
            'gen_ai.usage.output_tokens',
            'llm.token_count.completion',
            'token_count.completion',
            'completion_tokens',
        ]

        # Process each LLM span
        for span in trace_spans:
            attributes = self._key_value_list_to_dict(span.get('attributes', []))
            span_kind = span.get('kind', '')

            # Identify LLM call spans
            is_llm_call = (
                span_kind == 'LLM' or
                'gen_ai.system' in attributes or
                'gen_ai.request.model' in attributes or
                'llm.model_name' in attributes or
                'llm' in span.get('name', '').lower()
            )

            if is_llm_call:
                # Extract model name
                model_name = (
                    attributes.get('gen_ai.request.model') or
                    attributes.get('gen_ai.response.model') or
                    attributes.get('llm.model_name') or
                    attributes.get('gen_ai.system')
                )

                # Get pricing for this model
                pricing = self._get_model_pricing(model_name) if model_name else None

                if pricing:
                    # Extract token counts for this span
                    prompt_tokens = 0
                    completion_tokens = 0

                    for key in input_token_keys:
                        if key in attributes:
                            value = attributes[key]
                            try:
                                prompt_tokens = int(float(value))
                                break
                            except (ValueError, TypeError):
                                continue

                    for key in output_token_keys:
                        if key in attributes:
                            value = attributes[key]
                            try:
                                completion_tokens = int(float(value))
                                break
                            except (ValueError, TypeError):
                                continue

                    # Calculate costs (pricing is per 1M tokens)
                    span_prompt_cost = (prompt_tokens / 1_000_000) * pricing['prompt']
                    span_completion_cost = (completion_tokens / 1_000_000) * pricing['completion']

                    total_prompt_cost += span_prompt_cost
                    total_completion_cost += span_completion_cost

        total_cost = total_prompt_cost + total_completion_cost

        return {
            "total_cost": total_cost,
            "prompt_cost": total_prompt_cost,
            "completion_cost": total_completion_cost
        }

    def _write_trace(self, trace_id, trace_spans):
        """Write a complete trace object to the output file"""
        # Extract all metrics from spans
        root_span = next((s for s in trace_spans if s['parent_span_id'] is None), None)
        input_value = self._extract_input(root_span, trace_spans) if root_span else ""
        output_value = self._extract_output(root_span, trace_spans) if root_span else ""
        timestamp = self._extract_timestamp(root_span) if root_span else None
        duration_ms = self._extract_duration_ms(root_span) if root_span else None
        session_id = self._extract_session_id(root_span, trace_spans) if root_span else ""
        total_token_count = self._extract_total_token_count(trace_spans)
        prompt_token_count = self._extract_prompt_token_count(trace_spans)
        completion_token_count = self._extract_completion_token_count(trace_spans)

        # Extract tool call metrics
        tool_metrics = self._extract_tool_metrics(trace_spans)

        # Extract LLM call metrics
        llm_metrics = self._extract_llm_metrics(trace_spans)

        # Extract call sequence
        call_sequence = self._extract_call_sequence(trace_spans)

        # Extract trace-level status
        trace_status = self._extract_trace_status(trace_spans)

        # Calculate costs
        costs = self._calculate_costs(trace_spans)

        # Decode session_id (it's JSON-encoded from span attributes)
        # input/output are already JSON-encoded from span attributes, keep as-is
        decoded_session_id = session_id
        if session_id and session_id.startswith('"') and session_id.endswith('"'):
            try:
                decoded_session_id = json.loads(session_id)
            except (json.JSONDecodeError, ValueError):
                pass

        trace_object = {
            "trace_id": trace_id,
            "session_id": decoded_session_id,
            "input": input_value if input_value else "",
            "output": output_value if output_value else "",
            "timestamp": timestamp,
            "duration_ms": duration_ms,
            "status": trace_status["status"],
            "status_message": trace_status["status_message"],
            "total_token_count": total_token_count,
            "prompt_token_count": prompt_token_count,
            "completion_token_count": completion_token_count,
            "total_cost": costs["total_cost"],
            "prompt_cost": costs["prompt_cost"],
            "completion_cost": costs["completion_cost"],
            "tool_call_count": tool_metrics["tool_call_count"],
            "tool_call_error_count": tool_metrics["tool_call_error_count"],
            "tool_call_name_counts": tool_metrics["tool_call_name_counts"],
            "llm_call_count": llm_metrics["llm_call_count"],
            "llm_call_error_count": llm_metrics["llm_call_error_count"],
            "llm_call_model_counts": llm_metrics["llm_call_model_counts"],
            "call_sequence": call_sequence,
            "spans": trace_spans
        }

        json_line = json.dumps(trace_object) + '\n'
        self.file.write(json_line)
        self.file.flush()

    def shutdown(self):
        """Write any remaining traces on shutdown"""
        for trace_id, trace_spans in self.traces.items():
            self._write_trace(trace_id, trace_spans)
        self.file.close()
