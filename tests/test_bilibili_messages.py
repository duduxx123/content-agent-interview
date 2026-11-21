import base64
import unittest

from blivedm.models import pb, web as web_models


class SendGiftV2Tests(unittest.TestCase):
    def test_parse_protobuf_gift(self) -> None:
        gift = pb.SendGiftV2Gift(
            gift_id=1,
            gift_name="辣条",
            num=10,
            gift_type=1,
            price=100,
            total_coin=1000,
            coin_type="gold",
            timestamp=1700000000,
            action="投喂",
        )
        payload = {
            "pb": base64.b64encode(pb.SendGiftV2(gift=gift).dumps()).decode()
        }
        message = web_models.SendGiftV2Message.from_command(payload)
        self.assertEqual(message.gift_name, "辣条")
        self.assertEqual(message.num, 10)
        self.assertEqual(message.total_coin, 1000)
        self.assertEqual(message.coin_type, "gold")
        self.assertEqual(message.timestamp, 1700000000)

    def test_invalid_payload_is_ignored(self) -> None:
        message = web_models.SendGiftV2Message.from_command({"pb": "not-base64"})
        self.assertEqual(message.gift_name, "")
        self.assertEqual(message.num, 0)


if __name__ == "__main__":
    unittest.main()
