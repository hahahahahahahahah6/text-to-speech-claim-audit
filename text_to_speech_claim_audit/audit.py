"""Offline documentation and Python AST audit."""
import argparse
import ast
import json
import os
from pathlib import Path
import re
import sys

from .phrases import claims


def evidence(source):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    aliases = {}
    shadows = set()
    # Imports are resolved within this module; local definitions override them.
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name.split('.')[0]] = item.name if item.asname else item.name.split('.')[0]
        elif isinstance(node, ast.ImportFrom):
            for item in node.names:
                aliases[item.asname or item.name] = (node.module or '') + '.' + item.name
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            shadows.add(node.name)
        elif isinstance(node, ast.arg):
            shadows.add(node.arg)
    bindings = {}
    assignments = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    assignments.append((target.id, node.value))
                    shadows.add(target.id)

    def resolved(node):
        if isinstance(node, ast.Name):
            return '' if node.id in shadows else aliases.get(node.id, '')
        if isinstance(node, ast.Attribute):
            base = resolved(node.value)
            return base + '.' + node.attr if base else ''
        return ''

    def kind(node):
        if isinstance(node, ast.Name):
            return bindings.get(node.id)
        if not isinstance(node, ast.Call):
            return None
        name = resolved(node.func)
        if name == 'pyttsx3.init':
            return 'engine'
        if name == 'gtts.gTTS':
            return 'gtts'
        if name == 'edge_tts.Communicate':
            return 'edge'
        if name.startswith('TTS.api.') and name.endswith('.TTS'):
            return 'coqui'
        if name == 'kokoro.KPipeline':
            return 'kokoro'
        if name == 'win32com.client.Dispatch' and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str) and 'SAPI.SpVoice' in node.args[0].value:
            return 'sapi'
        return None

    for _ in range(len(assignments) + 1):
        for target, value in assignments:
            bindings[target] = kind(value)
    methods = {'engine': {'say', 'save_to_file'}, 'gtts': {'save', 'write_to_fp'}, 'edge': {'save', 'stream'}, 'coqui': {'tts', 'tts_to_file'}, 'sapi': {'Speak'}}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = resolved(node.func)
        if name.startswith('bark.') and name.endswith('.generate_audio'):
            return True
        if name == 'transformers.pipeline':
            args = list(node.args[:1]) + [kw.value for kw in node.keywords if kw.arg == 'task']
            if any(isinstance(arg, ast.Constant) and arg.value == 'text-to-speech' for arg in args):
                return True
        func = node.func
        if isinstance(func, ast.Name) and kind(func) == 'kokoro':
            return True
        if isinstance(func, ast.Call) and kind(func) == 'kokoro':
            return True
        if isinstance(func, ast.Attribute):
            if func.attr in methods.get(kind(func.value), set()):
                return True
            if func.attr == 'create' and isinstance(func.value, ast.Attribute) and func.value.attr == 'speech' and isinstance(func.value.value, ast.Attribute) and func.value.value.attr == 'audio':
                return True
    return False


def prose(text):
    lines = []
    fence = None
    for line in text.splitlines():
        match = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence) and not match[2].strip():
                fence = None
            lines.append('')
        elif match:
            fence = match[1]
            lines.append('')
        else:
            lines.append(line)
    return re.split(r'\n\s*\n', '\n'.join(lines))


def audit(root, ignore=()):
    root = Path(root)
    if not root.is_dir() or not os.access(root, os.R_OK | os.X_OK):
        raise OSError('root must be a readable directory')
    def ignored(rel):
        return any(rel == prefix.rstrip('/') or rel.startswith(prefix.rstrip('/') + '/')
                   for prefix in ignore)

    families = set()
    production = tests = False
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=lambda error: (_ for _ in ()).throw(error)):
        dirs[:] = sorted(d for d in dirs
                         if not Path(directory, d).is_symlink()
                         and not ignored(Path(directory, d).relative_to(root).as_posix()))
        for filename in sorted(files):
            path = Path(directory, filename)
            rel = path.relative_to(root)
            if path.is_symlink() or ignored(rel.as_posix()):
                continue
            if rel.as_posix() == 'README.md' or (path.suffix == '.md' and 'docs' in rel.parts[:-1]):
                for paragraph in prose(path.read_text(encoding='utf-8')):
                    families.update(claims(paragraph))
            if path.suffix != '.py' or {'fixtures', 'docs', 'examples'} & set(rel.parts[:-1]):
                continue
            hit = evidence(path.read_text(encoding='utf-8'))
            is_test = 'tests' in rel.parts[:-1] or filename.startswith('test_') or filename.endswith('_test.py')
            if is_test:
                tests |= hit
            else:
                production |= hit
    findings = []
    if 'TTS' in families and not production:
        findings.append({'rule': 'documented-tts-claim-false', 'severity': 'MEDIUM' if tests else 'HIGH', 'message': 'Evidence exists only in tests.' if tests else 'No production synthesis evidence.'})
    if 'NOTTS' in families and production:
        findings.append({'rule': 'documented-no-tts-claim-false', 'severity': 'HIGH', 'message': 'Production synthesis evidence contradicts documentation.'})
    return {'findings': findings, 'claims': sorted(families), 'production_evidence': production, 'test_evidence': tests}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, '%s: error: %s\n' % (self.prog, message))


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument('root', nargs='?', default='.')
    parser.add_argument('--version', action='version', version='0.1.0')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--ignore', action='append', default=[])
    parser.add_argument('--fail-on', choices=['HIGH', 'MEDIUM', 'LOW'], default='HIGH')
    args = parser.parse_args(argv)
    try:
        result = audit(args.root, args.ignore)
    except (OSError, UnicodeError) as error:
        print('error: %s' % error, file=sys.stderr)
        return 1
    ranks = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2}
    failed = any(ranks[f['severity']] >= ranks[args.fail_on] for f in result['findings'])
    result['status'] = 'FAIL' if failed else 'PASS'
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(result['status'])
        for finding in result['findings']:
            print('{severity} {rule}: {message}'.format(**finding))
        if args.verbose:
            print('Claims: %s; production evidence: %s; test evidence: %s' % (', '.join(result['claims']) or 'none', result['production_evidence'], result['test_evidence']))
    return 2 if failed else 0
