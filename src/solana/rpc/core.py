# pylint: disable=too-many-arguments
"""Helper code for api.py and async_api.py."""
from typing import List, Optional, Tuple, Union, cast, Sequence

try:
    from typing import Literal  # type: ignore
except ImportError:
    from typing_extensions import Literal  # type: ignore

import itertools

from solders.hash import Hash
from solders.pubkey import Pubkey
from solders.rpc.requests import (
    GetBalance,
    GetAccountInfo,
    GetBlockCommitment,
    GetBlockTime,
    GetClusterNodes,
    GetBlock,
    GetBlockHeight,
    GetRecentPerformanceSamples,
    GetBlocks,
    GetSignaturesForAddress,
    GetTransaction,
    GetEpochInfo,
    GetFeeForMessage,
    GetInflationGovernor,
    GetLargestAccounts,
    GetLeaderSchedule,
    GetMinimumBalanceForRentExemption,
    GetMultipleAccounts,
    GetProgramAccounts,
    GetLatestBlockhash,
    GetSignatureStatuses,
    GetSlot,
    GetSlotLeader,
    GetStakeActivation,
    GetSupply,
    GetTokenAccountBalance,
    GetTokenAccountsByDelegate,
    GetTokenAccountsByOwner,
    GetTokenLargestAccounts,
    GetTokenSupply,
    GetTransactionCount,
    GetVoteAccounts,
    RequestAirdrop,
    SendTransaction,
    SimulateTransaction,
    GetVersion,
    GetEpochSchedule,
    GetFirstAvailableBlock,
    GetGenesisHash,
    GetIdentity,
    GetInflationRate,
    MinimumLedgerSlot,
    ValidatorExit,
    GetHealth,
    GetBlockProduction,
    GetBlocksWithLimit,
    IsBlockhashValid,
)
from solders.rpc.config import (
    RpcContextConfig,
    RpcAccountInfoConfig,
    RpcBlockConfig,
    RpcSignaturesForAddressConfig,
    RpcTransactionConfig,
    RpcLargestAccountsFilter,
    RpcLeaderScheduleConfig,
    RpcProgramAccountsConfig,
    RpcSignatureStatusConfig,
    RpcEpochConfig,
    RpcSupplyConfig,
    RpcTokenAccountsFilterMint,
    RpcTokenAccountsFilterProgramId,
    RpcGetVoteAccountsConfig,
    RpcRequestAirdropConfig,
    RpcSendTransactionConfig,
    RpcSimulateTransactionConfig,
    RpcBlockProductionConfig,
    RpcBlockProductionConfigRange
)
from solders.rpc.filter import Memcmp
from solders.account_decoder import UiAccountEncoding, UiDataSliceConfig
from solders.transaction_status import UiTransactionEncoding
from solders.signature import Signature
from solders.commitment_config import CommitmentLevel
from solders.transaction import Transaction as SoldersTx

from solana.blockhash import Blockhash, BlockhashCache
from solana.message import Message
from solana.publickey import PublicKey
from solana.rpc import types
from solana.transaction import Transaction

from .commitment import Commitment, Finalized, Confirmed, Processed

_COMMITMENT_TO_SOLDERS = {
    Finalized: CommitmentLevel.Finalized,
    Confirmed: CommitmentLevel.Confirmed,
    Processed: CommitmentLevel.Processed,
}
_TX_ENCODING_TO_SOLDERS = {
    "binary": UiTransactionEncoding.Binary,
    "base58": UiTransactionEncoding.Base58,
    "base64": UiTransactionEncoding.Base64,
    "json": UiTransactionEncoding.Json,
    "jsonParsed": UiTransactionEncoding.JsonParsed,
}
_ACCOUNT_ENCODING_TO_SOLDERS = {
    "binary": UiAccountEncoding.Binary,
    "base58": UiAccountEncoding.Base58,
    "base64": UiAccountEncoding.Base64,
    "jsonParsed": UiAccountEncoding.JsonParsed,
    "base64+zstd": UiAccountEncoding.Base64Zstd,
}
_LARGEST_ACCOUNTS_FILTER_TO_SOLDERS = {
    "circulating": RpcLargestAccountsFilter.Circulating,
    "nonCirculating": RpcLargestAccountsFilter.NonCirculating,
}


class RPCException(Exception):
    """Raised when RPC method returns an error result."""


class RPCNoResultException(Exception):
    """Raised when an RPC method returns no result."""


class UnconfirmedTxError(Exception):
    """Raise when confirming a transaction times out."""


class TransactionExpiredBlockheightExceededError(Exception):
    """Raise when confirming an expired transaction that exceeded the blockheight."""


class TransactionUncompiledError(Exception):
    """Raise when transaction is not compiled to a message."""


class _ClientCore:  # pylint: disable=too-few-public-methods
    _comm_key = "commitment"
    _encoding_key = "encoding"
    _data_slice_key = "dataSlice"
    _skip_preflight_key = "skipPreflight"
    _preflight_comm_key = "preflightCommitment"
    _max_retries = "maxRetries"
    _before_rpc_config_key = "before"
    _limit_rpc_config_key = "limit"
    _until_rpc_config_key = "until"

    def __init__(self, commitment: Optional[Commitment] = None, blockhash_cache: Union[BlockhashCache, bool] = False):
        self._commitment = commitment or Finalized
        self.blockhash_cache: Union[BlockhashCache, Literal[False]] = (
            BlockhashCache()
            if blockhash_cache is True
            else cast(Union[BlockhashCache, Literal[False]], blockhash_cache)
        )
        self._session_request_count = itertools.count()

        self._get_cluster_nodes = GetClusterNodes(id=self._increment_counter_and_get_id())
        self._get_epoch_schedule = GetEpochSchedule(id=self._increment_counter_and_get_id())
        self._get_first_available_block = GetFirstAvailableBlock(id=self._increment_counter_and_get_id())
        self._get_genesis_hash = GetGenesisHash(id=self._increment_counter_and_get_id())
        self._get_identity = GetIdentity(id=self._increment_counter_and_get_id())
        self._get_inflation_rate = GetInflationRate(id=self._increment_counter_and_get_id())
        self._minimum_ledger_slot = MinimumLedgerSlot(id=self._increment_counter_and_get_id())
        self._get_version = GetVersion(id=self._increment_counter_and_get_id())
        self._validator_exit = ValidatorExit(id=self._increment_counter_and_get_id())
        self._get_health = GetHealth(id=self._increment_counter_and_get_id())

    @property
    def commitment(self) -> Commitment:
        """The default commitment used for requests."""
        return self._commitment

    def _increment_counter_and_get_id(self) -> int:
        return (next(self._session_request_count) + 1)

    def _get_blockhash_valid_body(self,
                                blockhash: Hash,
                                commitment: Optional[Commitment],
                                min_context_slot: Optional[int]) -> IsBlockhashValid:
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        return IsBlockhashValid(blockhash,
                                RpcContextConfig(commitment=commitment_to_use,
                                                            min_context_slot=min_context_slot
                                                            )
                                )
    def _get_balance_body(self, pubkey: PublicKey,
                          commitment: Optional[Commitment],
                          min_context_slot: Optional[int]) -> GetBalance:
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        return GetBalance(pubkey.to_solders(), RpcContextConfig(commitment=commitment_to_use,
                                                                min_context_slot=min_context_slot
                                                                )
                          )

    def _get_account_info_body(
        self,
        pubkey: PublicKey,
        commitment: Optional[Commitment],
        encoding: Optional[str],
        data_slice: Optional[types.DataSliceOpts],
        min_context_slot: Optional[int],
    ) -> GetAccountInfo:
        data_slice_to_use = (
            None if data_slice is None else UiDataSliceConfig(offset=data_slice.offset, length=data_slice.length)
        )
        encoding_to_use = _ACCOUNT_ENCODING_TO_SOLDERS[encoding] if encoding else encoding
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        config = RpcAccountInfoConfig(
            encoding=encoding_to_use, data_slice=data_slice_to_use, commitment=commitment_to_use,
            min_context_slot=min_context_slot
        )
        return GetAccountInfo(pubkey.to_solders(), config, id=self._increment_counter_and_get_id())

    def _get_block_commitment_body(self, slot: int) -> GetBlockCommitment:
        return GetBlockCommitment(slot=slot, id=self._increment_counter_and_get_id())

    def _get_block_time_body(self, slot: int) -> GetBlockTime:
        return GetBlockTime(slot=slot, id=self._increment_counter_and_get_id())

    def _get_block_body(self, slot: int, encoding: str) -> GetBlock:
        encoding_to_use = _TX_ENCODING_TO_SOLDERS[encoding]
        config = RpcBlockConfig(encoding=encoding_to_use)
        return GetBlock(slot=slot, config=config, id=self._increment_counter_and_get_id())

    def _get_block_height_body(self, commitment: Optional[Commitment],
                               min_context_slot: Optional[int]) -> GetBlockHeight:
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        return GetBlockHeight(RpcContextConfig(commitment=commitment_to_use,
                                               min_context_slot=min_context_slot
                                               ),
                              id=self._increment_counter_and_get_id()
                              )

    def _get_recent_performance_samples_body(self, limit: Optional[int]) -> GetRecentPerformanceSamples:
        return GetRecentPerformanceSamples(limit, id=self._increment_counter_and_get_id())

    def _get_blocks_body(self, start_slot: int, end_slot: Optional[int]) -> GetBlocks:
        return GetBlocks(start_slot, end_slot, id=self._increment_counter_and_get_id())

    def _get_signatures_for_address_body(
        self,
        address: PublicKey,
        before: Optional[Signature],
        until: Optional[Signature],
        limit: Optional[int],
        commitment: Optional[Commitment],
        min_context_slot: Optional[int] = None,
    ) -> GetSignaturesForAddress:
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        config = RpcSignaturesForAddressConfig(before=before,
                                               until=until,
                                               limit=limit,
                                               commitment=commitment_to_use,
                                               min_context_slot=min_context_slot)
        return GetSignaturesForAddress(address.to_solders(), config, id=self._increment_counter_and_get_id())

    def _get_transaction_body(
        self, tx_sig: Signature, encoding: str = "json", commitment: Commitment = None
    ) -> GetTransaction:
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        encoding_to_use = _TX_ENCODING_TO_SOLDERS[encoding]
        config = RpcTransactionConfig(encoding=encoding_to_use, commitment=commitment_to_use)
        return GetTransaction(tx_sig, config, id=self._increment_counter_and_get_id())

    def _get_epoch_info_body(self, commitment: Optional[Commitment], min_context_slot: Optional[int]) -> GetEpochInfo:
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        config = RpcContextConfig(commitment=commitment_to_use, min_context_slot=min_context_slot)
        return GetEpochInfo(config, id=self._increment_counter_and_get_id())
    def _get_fee_for_message_body(self, message: Message, commitment: Optional[Commitment]) -> GetFeeForMessage:
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        return GetFeeForMessage(message.to_solders(), commitment_to_use, id=self._increment_counter_and_get_id())

    def _get_inflation_governor_body(self, commitment: Optional[Commitment]) -> GetInflationGovernor:
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        return GetInflationGovernor(commitment_to_use, id=self._increment_counter_and_get_id())
    def _get_largest_accounts_body(
        self, filter_opt: Optional[str], commitment: Optional[Commitment]
    ) -> GetLargestAccounts:
        filter_to_use = None if filter_opt is None else _LARGEST_ACCOUNTS_FILTER_TO_SOLDERS[filter_opt]
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        return GetLargestAccounts(commitment=commitment_to_use, filter_=filter_to_use, id=self._increment_counter_and_get_id())

    def _get_leader_schedule_body(self, slot: Optional[int], commitment: Optional[Commitment]) -> GetLeaderSchedule:
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        config = RpcLeaderScheduleConfig(commitment=commitment_to_use)
        return GetLeaderSchedule(slot, config, id=self._increment_counter_and_get_id())

    def _get_minimum_balance_for_rent_exemption_body(
        self, usize: int, commitment: Optional[Commitment]
    ) -> GetMinimumBalanceForRentExemption:
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        return GetMinimumBalanceForRentExemption(usize, commitment_to_use, id=self._increment_counter_and_get_id())

    def _get_multiple_accounts_body(
        self,
        pubkeys: List[PublicKey],
        commitment: Optional[Commitment],
        encoding: str,
        data_slice: Optional[types.DataSliceOpts],
        min_context_slot: Optional[int],
    ) -> GetMultipleAccounts:
        accounts = [pubkey.to_solders() for pubkey in pubkeys]
        encoding_to_use = _ACCOUNT_ENCODING_TO_SOLDERS[encoding]
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        data_slice_to_use = (
            None if data_slice is None else UiDataSliceConfig(offset=data_slice.offset, length=data_slice.length)
        )
        config = RpcAccountInfoConfig(
            encoding=encoding_to_use,
            commitment=commitment_to_use,
            data_slice=data_slice_to_use,
            min_context_slot=min_context_slot
        )
        return GetMultipleAccounts(accounts, config, id=self._increment_counter_and_get_id())

    def _get_program_accounts_body(
        self,
        pubkey: PublicKey,
        commitment: Optional[Commitment],
        encoding: Optional[str],
        data_slice: Optional[types.DataSliceOpts],
        filters: Optional[Sequence[Union[int, types.MemcmpOpts]]] = None,
    ) -> GetProgramAccounts:  # pylint: disable=too-many-arguments
        encoding_to_use = None if encoding is None else _ACCOUNT_ENCODING_TO_SOLDERS[encoding]
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        data_slice_to_use = (
            None if data_slice is None else UiDataSliceConfig(offset=data_slice.offset, length=data_slice.length)
        )
        account_config = RpcAccountInfoConfig(
            encoding=encoding_to_use, commitment=commitment_to_use, data_slice=data_slice_to_use
        )
        filters_to_use: Optional[List[Union[int, Memcmp]]] = (
            None if filters is None else [x if isinstance(x, int) else Memcmp(*x) for x in filters]
        )
        config = RpcProgramAccountsConfig(account_config, filters_to_use)
        return GetProgramAccounts(pubkey.to_solders(), config, id=self._increment_counter_and_get_id())

    def _get_latest_blockhash_body(self,

                                   commitment: Optional[Commitment],
                                   min_context_slot: Optional[int]
                                   ) -> GetLatestBlockhash:
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        return GetLatestBlockhash(RpcContextConfig(commitment_to_use, min_context_slot=min_context_slot))

    # DEPRECATED
    def _get_block_production_body(self,
                                   first_slot:Optional[int],
                                   last_slot:Optional[int],
                                   identity:Optional[Pubkey],
                                   commitment: Optional[Commitment],
                                   ) -> GetBlockProduction:
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        if first_slot and last_slot:
            range = RpcBlockProductionConfigRange(first_slot=first_slot, last_slot=last_slot)
            config = RpcBlockProductionConfig(range=range, identity=identity, commitment=commitment_to_use)
        else:
            config = RpcBlockProductionConfig(commitment=commitment_to_use)
        return GetBlockProduction(config, id=self._increment_counter_and_get_id())

    # DEPRECATED
    def _get_blocks_with_limit_body(self,
                                    start: int,
                                    limit: Optional[int],
                                    commitment: Optional[Commitment]) -> GetBlocksWithLimit:
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        return GetBlocksWithLimit(start, limit, commitment_to_use, id=self._increment_counter_and_get_id())

    def _get_signature_statuses_body(self,
        signatures: List[Signature], search_transaction_history: bool
    ) -> GetSignatureStatuses:
        config = RpcSignatureStatusConfig(search_transaction_history)
        return GetSignatureStatuses(signatures, config, id=self._increment_counter_and_get_id())

    def _get_slot_body(self, commitment: Optional[Commitment], min_context_slot: Optional[int] = None) -> GetSlot:
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        return GetSlot(RpcContextConfig(commitment_to_use, min_context_slot), id=self._increment_counter_and_get_id())
    def _get_slot_leader_body(self, commitment: Optional[Commitment], min_context_slot: Optional[int] = None) -> GetSlotLeader:
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        return GetSlotLeader(RpcContextConfig(commitment_to_use, min_context_slot), id=self._increment_counter_and_get_id())

    def _get_stake_activation_body(
        self,
        pubkey: PublicKey,
        epoch: Optional[int],
        commitment: Optional[Commitment],
    ) -> GetStakeActivation:
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        return GetStakeActivation(pubkey.to_solders(), RpcEpochConfig(epoch, commitment_to_use), id=self._increment_counter_and_get_id())

    def _get_supply_body(self, commitment: Optional[Commitment]) -> GetSupply:
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        return GetSupply(RpcSupplyConfig(commitment=commitment_to_use, exclude_non_circulating_accounts_list=False), id=self._increment_counter_and_get_id())

    def _get_token_account_balance_body(
        self, pubkey: PublicKey, commitment: Optional[Commitment]
    ) -> GetTokenAccountBalance:
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        return GetTokenAccountBalance(pubkey.to_solders(), commitment_to_use, id=self._increment_counter_and_get_id())

    def _get_token_accounts_convert(
        self, pubkey: PublicKey, opts: types.TokenAccountOpts, commitment: Optional[Commitment]
    ) -> Tuple[Pubkey, Union[RpcTokenAccountsFilterMint, RpcTokenAccountsFilterProgramId], RpcAccountInfoConfig]:
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        encoding_to_use = _ACCOUNT_ENCODING_TO_SOLDERS[opts.encoding]
        maybe_data_slice = opts.data_slice
        data_slice_to_use = (
            None
            if maybe_data_slice is None
            else UiDataSliceConfig(offset=maybe_data_slice.offset, length=maybe_data_slice.length)
        )
        maybe_mint = opts.mint
        maybe_program_id = opts.program_id
        if maybe_mint is not None:
            filter_to_use = RpcTokenAccountsFilterMint(maybe_mint.to_solders())
        elif maybe_program_id is not None:
            filter_to_use = RpcTokenAccountsFilterMint(maybe_program_id.to_solders())
        else:
            raise ValueError("Please provide one of mint or program_id")
        config = RpcAccountInfoConfig(
            encoding=encoding_to_use, commitment=commitment_to_use, data_slice=data_slice_to_use
        )
        return pubkey.to_solders(), filter_to_use, config

    def _get_token_accounts_by_delegate_body(
        self, delegate: PublicKey, opts: types.TokenAccountOpts, commitment: Optional[Commitment]
    ) -> GetTokenAccountsByDelegate:
        pubkey, filter_, config = self._get_token_accounts_convert(delegate, opts, commitment)
        return GetTokenAccountsByDelegate(pubkey, filter_, config)

    def _get_token_accounts_by_owner_body(
        self, owner: PublicKey, opts: types.TokenAccountOpts, commitment: Optional[Commitment]
    ) -> GetTokenAccountsByOwner:
        pubkey, filter_, config = self._get_token_accounts_convert(owner, opts, commitment)
        return GetTokenAccountsByOwner(pubkey, filter_, config)

    def _get_token_largest_accounts_body(
        self, pubkey: PublicKey, commitment: Optional[Commitment]
    ) -> GetTokenLargestAccounts:
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        return GetTokenLargestAccounts(pubkey.to_solders(), commitment_to_use)

    def _get_token_supply_body(self, pubkey: PublicKey, commitment: Optional[Commitment]) -> GetTokenSupply:
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        return GetTokenSupply(pubkey.to_solders(), commitment_to_use)

    def _get_transaction_count_body(self, commitment: Optional[Commitment], min_context_slot: Optional[int]) -> GetTransactionCount:
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        return GetTransactionCount(RpcContextConfig(commitment_to_use, min_context_slot))

    def _get_vote_accounts_body(self, commitment: Optional[Commitment]) -> GetVoteAccounts:
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        config = RpcGetVoteAccountsConfig(commitment=commitment_to_use)
        return GetVoteAccounts(config)

    def _request_airdrop_body(
        self, pubkey: PublicKey, lamports: int, commitment: Optional[Commitment]
    ) -> RequestAirdrop:
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        return RequestAirdrop(pubkey.to_solders(), lamports, RpcRequestAirdropConfig(commitment=commitment_to_use))

    def _send_raw_transaction_body(self, txn: bytes, opts: types.TxOpts) -> SendTransaction:
        solders_tx = SoldersTx.from_bytes(txn)
        preflight_commitment_to_use = _COMMITMENT_TO_SOLDERS[opts.preflight_commitment or self._commitment]
        config = RpcSendTransactionConfig(
            skip_preflight=opts.skip_preflight,
            preflight_commitment=preflight_commitment_to_use,
            max_retries=opts.max_retries,
        )
        return SendTransaction(
            solders_tx,
            config,
        )

    @staticmethod
    def _send_raw_transaction_post_send_args(
        resp: types.RPCResponse, opts: types.TxOpts
    ) -> Tuple[types.RPCResponse, Commitment, Optional[int]]:
        return resp, opts.preflight_commitment, opts.last_valid_block_height

    def _simulate_transaction_body(
        self, txn: Transaction, sig_verify: bool, commitment: Optional[Commitment], min_context_slot: Optional[int]
    ) -> SimulateTransaction:
        if txn.recent_blockhash is None:
            raise ValueError("transaction must have a valid blockhash")
        commitment_to_use = _COMMITMENT_TO_SOLDERS[commitment or self._commitment]
        config = RpcSimulateTransactionConfig(
            sig_verify=sig_verify, commitment=commitment_to_use, min_context_slot=min_context_slot #, encoding=UiTransactionEncoding.Base64
        )
        return SimulateTransaction(txn.to_solders(), config)

    @staticmethod
    def _post_send(resp: types.RPCResponse) -> types.RPCResponse:
        error = resp.get("error")
        if error:
            raise RPCException(error)
        if not resp.get("result"):
            raise RPCNoResultException("Failed to send transaction")
        return resp

    @staticmethod
    def parse_recent_blockhash(blockhash_resp: types.RPCResponse) -> Blockhash:
        """Extract blockhash from JSON RPC result."""
        if not blockhash_resp.get("result"):
            raise RuntimeError("failed to get recent blockhash")
        return Blockhash(blockhash_resp["result"]["value"]["blockhash"])

    def _process_blockhash_resp(self, blockhash_resp: types.RPCResponse, used_immediately: bool) -> Blockhash:
        recent_blockhash = self.parse_recent_blockhash(blockhash_resp)
        if self.blockhash_cache:
            slot = blockhash_resp["result"]["context"]["slot"]
            self.blockhash_cache.set(recent_blockhash, slot, used_immediately=used_immediately)
        return recent_blockhash
