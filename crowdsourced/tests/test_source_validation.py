from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from validate import metadata_errors


class SourceValidationTests(unittest.TestCase):
    def fixture(self):
        return dict(name='Fixture',record_kind='source_page',url='https://vgsoharchive.com/world/fixture',
                    fields={'continent':['Thestra']},headings=['Quests'],referenced_entities=['https://vgsoharchive.com/quests/fixture'])

    def test_source_metadata_allows_unknown_sections_on_older_batches(self):
        self.assertEqual(metadata_errors(self.fixture()),[])

    def test_query_and_external_references_are_invalid(self):
        r=self.fixture()
        r['referenced_entities']=['https://vgsoharchive.com/items?class=1','https://example.org/item']
        self.assertIn('source-page references must be canonical archive URLs',metadata_errors(r))

    def test_long_field_prose_is_not_short_fact_metadata(self):
        r=self.fixture()
        r['fields']={'guide':['word '*26]}
        self.assertIn('source-page fields must contain short string lists',metadata_errors(r))

    def test_malformed_section_link_is_reported(self):
        r=self.fixture()
        r['sections']=[dict(heading='Quests',linked_entities=[dict(name='Fixture',url=42)])]
        self.assertIn('invalid source-page section link',metadata_errors(r))
