import email
import unittest

from tldr_ai_briefing import decode_mime_header, is_link_rich_newsletter


def make_message(link_count: int) -> email.message.Message:
    links = "".join(
        f'<a href="https://example.com/article-{index}">Article</a>'
        for index in range(link_count)
    )
    return email.message_from_string(
        "Content-Type: text/html\n"
        "\n"
        f"<html><body>{links}</body></html>"
    )


class NewsletterSelectionTests(unittest.TestCase):
    def test_unknown_header_charset_falls_back_to_utf8(self) -> None:
        raw_header = "=?unknown-8bit?b?VExEUiBBSSBuZXdzbGV0dGVy?="

        self.assertEqual(decode_mime_header(raw_header), "TLDR AI newsletter")

    def test_link_rich_message_is_eligible_newsletter(self) -> None:
        self.assertTrue(is_link_rich_newsletter(make_message(5)))

    def test_sparse_sender_message_is_not_eligible_newsletter(self) -> None:
        self.assertFalse(is_link_rich_newsletter(make_message(4)))


if __name__ == "__main__":
    unittest.main()
