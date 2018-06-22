from unittest import TestCase

import simplejson as json
from mock import patch, Mock, PropertyMock
from pyqrllib.pyqrllib import bin2hstr

from qrl.core.AddressState import AddressState
from qrl.core.misc import logger
from qrl.core.txs.MessageTransaction import MessageTransaction
from qrl.core.txs.Transaction import Transaction
from tests.core.txs.testdata import test_json_MessageTransaction, test_signature_MessageTransaction
from tests.misc.helper import get_alice_xmss, get_bob_xmss

logger.initialize_default()


@patch('qrl.core.txs.Transaction.logger')
class TestMessageTransaction(TestCase):

    def setUp(self):
        self.alice = get_alice_xmss()
        self.bob = get_bob_xmss()

        self.alice.set_ots_index(10)
        self.maxDiff = None

        self.params = {
            "message_hash": b'Test Message',
            "fee": 1,
            "xmss_pk": self.alice.pk
        }

    def test_create(self, m_logger):
        tx = MessageTransaction.create(message_hash=b'Test Message',
                                       fee=1,
                                       xmss_pk=self.alice.pk)
        self.assertTrue(tx)

    def test_to_json(self, m_logger):
        tx = MessageTransaction.create(message_hash=b'Test Message',
                                       fee=1,
                                       xmss_pk=self.alice.pk)
        txjson = tx.to_json()

        self.assertEqual(json.loads(test_json_MessageTransaction), json.loads(txjson))

    def test_from_json(self, m_logger):
        tx = Transaction.from_json(test_json_MessageTransaction)
        tx.sign(self.alice)

        self.assertIsInstance(tx, MessageTransaction)

        # Test that common Transaction components were copied over.
        self.assertEqual('010300a1da274e68c88b0ccf448e0b1916fa789b01eb2ed4e9ad565ce264c9390782a9c61ac02f',
                         bin2hstr(tx.addr_from))
        self.assertEqual('01030038ea6375069f8272cc1a6601b3c76c21519455603d370036b97c779ada356'
                         '5854e3983bd564298c49ae2e7fa6e28d4b954d8cd59398f1225b08d6144854aee0e',
                         bin2hstr(tx.PK))
        self.assertEqual(b'Test Message', tx.message_hash)
        self.assertEqual('cbe7c40a86e82b8b6ac4e7df812f882183bd85d60f335cd83483d6831e61f4ec', bin2hstr(tx.txhash))
        self.assertEqual(10, tx.ots_key)

        self.assertEqual(test_signature_MessageTransaction, bin2hstr(tx.signature))

        self.assertEqual(1, tx.fee)

    def test_validate_tx(self, m_logger):
        tx = MessageTransaction.create(**self.params)

        # We must sign the tx before validation will work.
        tx.sign(self.alice)

        # We have not touched the tx: validation should pass.
        self.assertTrue(tx.validate_or_raise())

    def test_validate_tx2(self, m_logger):
        self.params["message_hash"] = b'T' * 81

        # Validation should fail, as we have entered a message of more than 80 lengths
        with self.assertRaises(ValueError):
            MessageTransaction.create(**self.params)

    def test_validate_message_length_zero(self, m_logger):
        self.params["message_hash"] = b''
        with self.assertRaises(ValueError):
            MessageTransaction.create(**self.params)

    @patch('qrl.core.txs.Transaction.Transaction.validate_slave', return_value=True)
    def test_validate_extended(self, m_validate_slave, m_logger):
        """
        Message.validate_extended checks for:
        1. valid master/slave
        2. negative fee, negative total token amounts transferred
        3. addr_from has enough funds for the fee
        4. addr_from ots_key reuse
        """
        m_addr_from_state = Mock(autospec=AddressState, name='addr_from State', balance=100)

        m_addr_from_pk_state = Mock(autospec=AddressState, name='addr_from_pk State')
        m_addr_from_pk_state.ots_key_reuse.return_value = False

        tx = MessageTransaction.create(**self.params)
        tx.sign(self.alice)

        result = tx.validate_extended(m_addr_from_state, m_addr_from_pk_state)
        self.assertTrue(result)

        # Invalid master XMSS/slave XMSS relationship
        m_validate_slave.return_value = False
        result = tx.validate_extended(m_addr_from_state, m_addr_from_pk_state)
        self.assertFalse(result)
        m_validate_slave.return_value = True

        # fee = -1
        with patch('qrl.core.txs.MessageTransaction.MessageTransaction.fee', new_callable=PropertyMock) as m_fee:
            m_fee.return_value = -1
            result = tx.validate_extended(m_addr_from_state, m_addr_from_pk_state)
            self.assertFalse(result)

        # balance = 0, cannot pay the Transaction fee
        m_addr_from_state.balance = 0
        result = tx.validate_extended(m_addr_from_state, m_addr_from_pk_state)
        self.assertFalse(result)
        m_addr_from_state.balance = 100

        # addr_from_pk has used this OTS key before
        m_addr_from_pk_state.ots_key_reuse.return_value = True
        result = tx.validate_extended(m_addr_from_state, m_addr_from_pk_state)
        self.assertFalse(result)

    def test_set_affected_address(self, m_logger):
        result = set()
        tx = MessageTransaction.create(**self.params)
        tx.set_affected_address(result)
        self.assertEqual(1, len(result))
