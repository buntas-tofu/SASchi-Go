"""Read-only operation-tree traversal shared by compilation and validation.

Walking a node does not execute it or admit its operation kind. The default
follows the supported control containers. Guard scans may inspect structural
containers of unknown kinds as well, preserving conservative source checks.
"""
from collections.abc import Mapping


def walk_operations(ops, *, all_containers=False, _if_depth=0):
    """Yield original object/mapping nodes in source-order preorder.

    Compiled roots may contain serialized children. Preserve their identity and
    payloads, including statically present zero-trip bodies. Runtime execution
    retains its separate IF and DO scheduling and operation allowlists.
    """
    for op in ops:
        yield op
        kind, args = (op['kind'], op['args']) if isinstance(op, Mapping) else (op.kind, op.args)
        if kind == 'do_over' and (not isinstance(args, Mapping) or not isinstance(args.get('body'), list)
                or any(not isinstance(child, Mapping) or set(child) != {'kind', 'line', 'args'}
                       or not isinstance(child['args'], Mapping) for child in args['body'])):
            raise ValueError('DO OVER requires a list of well-formed body operations')
        if kind == 'if' and _if_depth >= 32:
            raise ValueError('IF branch nesting exceeds the bounded32-condition policy')
        if kind == 'if' or (all_containers and 'operation' in args):
            child = args.get('operation')
            if not isinstance(child, Mapping) and not (hasattr(child, 'kind') and hasattr(child, 'args')):
                raise ValueError('IF then branch must be an operation')
            yield from walk_operations([child], all_containers=all_containers, _if_depth=_if_depth + 1)
        if (kind == 'if' or all_containers) and 'otherwise' in args:
            child = args['otherwise']
            if not isinstance(child, Mapping) and not (hasattr(child, 'kind') and hasattr(child, 'args')):
                raise ValueError('IF otherwise branch must be an operation')
            yield from walk_operations([child], all_containers=all_containers, _if_depth=_if_depth + 1)
        if kind in ('do_counted', 'do_until', 'do_while', 'do_over') or (all_containers and 'body' in args):
            body = args.get('body')
            if not isinstance(body, list):
                label = {'do_counted': 'counted DO', 'do_until': 'DO UNTIL', 'do_while': 'DO WHILE'}.get(kind, 'operation')
                raise ValueError(f'{label} body must be a list')
            yield from walk_operations(body, all_containers=all_containers, _if_depth=_if_depth)
