"""C++17 pilot backend for scalar numeric DATA _NULL_ plans.

The compiler sees only validated names and binary64 constants. Unsupported
operations block the entire translation before any executable is produced.
"""
import math
from .plan import Ticket, compile_plan
from .emit_py import Translation


def translate(source: str) -> Translation:
    parsed = compile_plan(source)
    for step in parsed.steps:
        if step.kind != "data" or step.inputs or step.name != "_null_":
            parsed.tickets.append(Ticket(step.line, step.name, "cpp-target", "C++ pilot supports scalar DATA _NULL_ steps only"))
        if step.where or step.retained or step.lengths:
            parsed.tickets.append(Ticket(step.line, step.name, 'cpp-target', 'state and metadata are outside the scalar pilot'))
        for op in step.operations:
            if (op.kind == 'put' and '_n_' in op.args['names']) or op.kind not in ('assign', 'round', 'put') or any(
                    expr.get('kind') not in ('number', 'missing', 'variable')
                    for expr in (op.args.get('value', {}), op.args.get('unit', {})) if expr):
                parsed.tickets.append(Ticket(op.line, op.kind, 'cpp-target', 'operation is outside the scalar numeric pilot'))
    plan = parsed.to_dict()
    if parsed.blocked:
        return Translation('// BLOCKED: unsupported plan for the C++ scalar pilot.\n#error "saschi: blocked translation"\n',
                           parsed.matched, parsed.tickets, True, plan)
    lines = ['// Scope: scalar DATA _NULL_; binary64 values; repository fixture evidence.',
             '#include <cmath>', '#include <iomanip>', '#include <iostream>', '#include <limits>',
             '#include <map>', '#include <string>',
             'static double missing() { return std::numeric_limits<double>::quiet_NaN(); }',
             'static double get(const std::map<std::string,double>& v, const std::string& n) {',
             '  auto i=v.find(n); return i==v.end() ? missing() : i->second;', '}',
             'static double round_value(double x,double u) {',
             '  if (!std::isfinite(x) || !std::isfinite(u) || u<=0) return missing();',
             '  double y=std::copysign(std::floor(std::abs(x)/u+0.5+1e-9)*u,x);',
             '  return std::isfinite(y) ? y : missing();', '}',
             'static void put(double x) { if(std::isnan(x)) std::cout << "."; else std::cout << std::setprecision(17) << x; }',
             'int main() {']

    def atom(expr):
        if expr['kind'] == 'missing':
            return 'missing()'
        if expr['kind'] == 'variable':
            return 'get(v,"' + expr['value'] + '")'
        return repr(expr['value'])

    for step in parsed.steps:
        lines += [f'// SAS line {step.line}', '{ std::map<std::string,double> v;']
        for op in step.operations:
            args = op.args
            lines.append(f'// SAS line {op.line}')
            if op.kind == 'assign':
                lines.append('v["' + args['name'] + '"]=' + atom(args['value']) + ';')
            elif op.kind == 'round':
                lines.append('v["' + args['name'] + '"]=round_value(' + atom(args['value']) + ',' + atom(args['unit']) + ');')
            elif op.kind == 'put':
                for index, name in enumerate(args['names']):
                    lines.append('std::cout << "' + (' ' if index else '') + name + '="; put(get(v,"' + name + '"));')
                lines.append('std::cout << "\\n";')
        lines.append('}')
    lines += ['return 0;', '}']
    return Translation('\n'.join(lines) + '\n', parsed.matched, [], False, plan)
