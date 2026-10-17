import importlib.util
import itertools
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('h3_sheet_test_pack', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
pack = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = pack
spec.loader.exec_module(pack)
FLOW = json.loads((ROOT / 'example_workflows/H3 Single Image Fizgig - Public.json').read_text())
NODES = {n['id']: n for n in FLOW['nodes']}


def widget_args(node):
    names = [s['name'] for s in node['inputs'] if s.get('widget') and s['name'] != 'preview']
    return dict(zip(names, node['widgets_values']))


class PublicWorkflowTests(unittest.TestCase):
    def test_links_and_reachability(self):
        links = {l[0]: l for l in FLOW['links']}
        self.assertEqual(len(links), len(FLOW['links']))
        self.assertEqual(len(NODES), len(FLOW['nodes']))
        for lid, source, out_slot, target, in_slot, kind in links.values():
            out = NODES[source]['outputs'][out_slot]
            inp = NODES[target]['inputs'][in_slot]
            self.assertIn(lid, out['links'])
            self.assertEqual(inp['link'], lid)
            self.assertIn(kind, (out['type'], '*'))
            self.assertIn(inp['type'], (kind, '*'))
            self.assertLess(NODES[source]['order'], NODES[target]['order'])
        for node in NODES.values():
            for i, slot in enumerate(node.get('inputs', [])):
                if slot.get('link') is not None:
                    self.assertEqual(links[slot['link']][3:5], [node['id'], i])
            for i, slot in enumerate(node.get('outputs', [])):
                for lid in slot.get('links') or []:
                    self.assertEqual(links[lid][1:3], [node['id'], i])
        reachable = {19, 29}
        while True:
            more = reachable | {s for _, s, _, t, _, _ in links.values() if t in reachable}
            if more == reachable:
                break
            reachable = more
        functional = {n['id'] for n in NODES.values() if n['type'] != 'MarkdownNote'}
        self.assertEqual(functional, reachable, 'Every functional node must feed an output')

    def test_no_overlapping_nodes_or_groups(self):
        for a, b in itertools.combinations(NODES.values(), 2):
            x, y = a['pos']; w, h = a['size']
            bx, by = b['pos']; bw, bh = b['size']
            overlaps = x < bx+bw and bx < x+w and y-30 < by+bh and by-30 < y+h
            self.assertFalse(overlaps, (a['id'], b['id']))
        for a, b in itertools.combinations(FLOW['groups'], 2):
            x, y, w, h = a['bounding']; bx, by, bw, bh = b['bounding']
            self.assertFalse(x < bx+bw and bx < x+w and y < by+bh and by < y+h)

    def test_all_sheet_choices_and_reference_counts(self):
        subjects = pack.NODE_CLASS_MAPPINGS['H3Subjects']()
        slots = pack.NODE_CLASS_MAPPINGS['H3RefSlots']()
        compose = pack.NODE_CLASS_MAPPINGS['H3ImagePromptCompose']()
        subject_text = subjects.build(**widget_args(NODES[26]))[0]
        template_links = {NODES[5915]['inputs'][ts]['name']: s
                          for _, s, _, t, ts, _ in FLOW['links'] if t == 5915}
        self.assertEqual(set(template_links), {f'value{i}' for i in range(7)})
        for count, index in itertools.product((1, 3, 9), range(7)):
            with self.subTest(references=count, sheet=index):
                args = widget_args(NODES[27])
                for i in range(1, 10):
                    args[f'pic_{i}'] = ('face (primary)' if i == 1 else 'face') if i <= count else 'unused'
                bindings = slots.build(subject_text, **args)[0]
                description = NODES[template_links[f'value{index}']]['widgets_values'][0]
                prompt, report = compose.compose(bindings, description, True, 'A silent still image.')
                for heading in ('subject_definitions:', 'summary:', 'retention_analysis:', 'detailed_description:', 'overall_soundscape:'):
                    self.assertEqual(prompt.count(heading), 1, heading)
                self.assertEqual({int(n) for n in re.findall(r'<Picture (\d+)>', prompt)}, set(range(1, count+1)))
                self.assertNotIn('<Subject 2>', prompt)
                self.assertNotIn('<Video ', prompt)
                self.assertNotIn('<Audio ', prompt)
                self.assertIn(f'{count} picture ref(s)', report)
                self.assertIn('<Subject 1>', prompt)

    def test_sheet_roles_and_attribute_binding(self):
        subjects = pack.NODE_CLASS_MAPPINGS['H3Subjects']().build(**widget_args(NODES[26]))[0]
        slots = pack.NODE_CLASS_MAPPINGS['H3RefSlots']()
        compose = pack.NODE_CLASS_MAPPINGS['H3ImagePromptCompose']()
        for role in ('face sheet', 'character sheet', 'face + hair', 'body', 'outfit'):
            with self.subTest(role=role):
                args = widget_args(NODES[27]); args['pic_1'] = role
                binding = slots.build(subjects, **args)[0]
                prompt, report = compose.compose(binding, 'One portrait of <Subject 1>.', True)
                self.assertIn('<Picture 1>', prompt)
                self.assertNotIn('<Picture 2>', prompt)
                self.assertIn('1 picture ref(s)', report)

    def test_public_defaults_and_fizgig_path(self):
        refs = [7, 8, 9, 10, 31, 41, 42, 5897, 6000]
        incoming = {NODES[22]['inputs'][ts]['name']: s for _, s, _, t, ts, _ in FLOW['links'] if t == 22}
        self.assertEqual(incoming, {f'images.image_{i}': nid for i, nid in enumerate(refs)})
        for i, nid in enumerate(refs):
            self.assertEqual(NODES[nid]['mode'], 0 if i == 0 else 4)
            self.assertEqual(NODES[nid]['widgets_values'][0], f'UPLOAD_REFERENCE_{i+1}.png')
        self.assertEqual(sum(n['type'] == 'H3ImagePromptCompose' for n in NODES.values()), 1)
        self.assertFalse(any('Glimmer' in n['type'] or n['type'] == 'H3SubjectDescFromRefs' for n in NODES.values()))
        self.assertEqual({n['type'] for n in NODES.values() if n['type'] in pack.NODE_CLASS_MAPPINGS}, set(pack.NODE_CLASS_MAPPINGS))
        links = {l[0]: l for l in FLOW['links']}
        latent = next(s for s in NODES[16]['inputs'] if s['name'] == 'latent_image')
        self.assertEqual(links[latent['link']][1], 5898)
        self.assertFalse(NODES[23]['outputs'][1]['links'])
        for target in (23, 5898):
            for name in ('width', 'height'):
                slot = next(s for s in NODES[target]['inputs'] if s['name'] == name)
                self.assertEqual(links[slot['link']][1], 30)
        self.assertEqual(NODES[5915]['widgets_values'], [0])
        self.assertEqual(NODES[30]['widgets_values'][-1], 32)


if __name__ == '__main__':
    unittest.main()
