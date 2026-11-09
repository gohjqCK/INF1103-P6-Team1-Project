import unittest

from ai_manager_modules.ai_manager_text_matcher import TextMatcher


class TestContains(unittest.TestCase):

    def test_ignores_case_and_punctuation(self):
        matcher = TextMatcher("Skills: CISCO-IOS, Python.")
        self.assertTrue(matcher.contains("cisco ios"))

    def test_matches_inside_a_longer_word(self):
        matcher = TextMatcher("Skills: JavaScript")
        self.assertTrue(matcher.contains("Java"))

    def test_empty_phrase_is_not_found(self):
        matcher = TextMatcher("Skills: Python")
        self.assertFalse(matcher.contains(""))

    def test_fixes_pdf_ligature(self):
        matcher = TextMatcher("\ufb01rewall")
        self.assertTrue(matcher.contains("firewall"))


class TestHasAnyWord(unittest.TestCase):

    def test_finds_one_of_the_words(self):
        matcher = TextMatcher("Palo Alto firewalls")
        self.assertTrue(matcher.has_any_word(["firewall", "firewalls"]))

    def test_needs_a_whole_word(self):
        matcher = TextMatcher("Skills: JavaScript")
        self.assertFalse(matcher.has_any_word(["Java"]))

    def test_short_word_not_found_inside_another(self):
        matcher = TextMatcher("Network security")
        self.assertFalse(matcher.has_any_word(["IT"]))

    def test_empty_list_finds_nothing(self):
        matcher = TextMatcher("Skills: Python")
        self.assertFalse(matcher.has_any_word([]))


if __name__ == "__main__":
    unittest.main()