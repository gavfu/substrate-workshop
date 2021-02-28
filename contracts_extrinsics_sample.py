import os
from scalecodec.type_registry import load_type_registry_file, load_type_registry_preset
from substrateinterface import SubstrateInterface, Keypair
from substrateinterface.contracts import ContractCode, ContractInstance, ContractMetadata
from scalecodec.utils.ss58 import ss58_encode
from scalecodec import ScaleBytes
from scalecodec.base import ScaleDecoder, ScaleType, RuntimeConfiguration

# Copied from Metadata.generate_message_data
def generate_message_data(substrate: SubstrateInterface, contract: ContractInstance, name, args: dict = None) -> ScaleBytes:
  if not args:
    args = {}
  for message in contract.metadata.metadata_dict['spec']['messages']:
    if name in message['name']:
      data = ScaleBytes(message['selector'])
      print("message['selector']: {}, data: {}".format(message['selector'], data))
      
      for arg in message['args']:
        if arg['name'] not in args:
          raise ValueError(f"Argument \"{arg['name']}\" is missing")
        else:
          data += substrate.encode_scale(
              type_string=contract.metadata.get_type_string_for_metadata_type(arg['type']['type']),
              value=args[arg['name']]
          )
          print("arg name: {}, type: {}, type string: {}, data: {}".format(arg['name'], arg['type']['type'], contract.metadata.get_type_string_for_metadata_type(arg['type']['type']), data))
      return data
  raise ValueError(f'Message "{name}" not found')


def decode_message_data(substrate: SubstrateInterface, contract: ContractInstance, data: str) -> dict:
  # Decode message selector
  result = {}

  for message in contract.metadata.metadata_dict['spec']['messages']:

    if data.startswith(message['selector']):
      result['name'] = message['name'][0]
      args_data = data[len(message['selector']):]
      print("decode_message_data, message: {}".format(message))
      print("decode_message_data, args: {}".format(args_data))

      # Parse args
      result['args'] = []
      remaining_args_data = args_data
      for arg in message['args']:
        type_str = contract.metadata.get_type_string_for_metadata_type(arg['type']['type'])
        print("decode_message_data, arg type string: {}".format(type_str))
        
        arg_value = remaining_args_data
        value_len = len(arg_value)
        if type_str == 'AccountId':
          value_len = 64
        arg_value = '0x' + remaining_args_data[0:value_len]
        remaining_args_data = remaining_args_data[value_len:]

        obj = ScaleDecoder.get_decoder_class( 
            type_string=type_str,
            # data=ScaleBytes('0x8eaf04151687736326c9fea17e25fc5287613693c912909cb226aa4794f26a48'),
            data=ScaleBytes(arg_value),
            metadata=substrate.metadata_decoder,
            runtime_config=substrate.runtime_config
        )
        print("decode_message_data, arg type decoder class: {}".format(type(obj)))
        obj.decode()
        print("decode_message_data, arg decoded value: {}".format(obj.value))
        
        result['args'].append({
          'name': arg['name'],
          'value': obj.value
        })

  return result


def main():
  aquasphere_type_registry = load_type_registry_file("./aquasphere_types.json")

  substrate = SubstrateInterface(
      url="wss://rpc-test.aquasphere.io",
      ss58_format=42,
      type_registry_preset='substrate-node-template',
      type_registry=aquasphere_type_registry
  )

  contract = ContractInstance.create_from_address(
      contract_address="5HjDz4zQTFXFFPVoHhp1EzNp38WB5DpdV4wt77qG8JtmnfXt",
      metadata_file=os.path.join(os.path.dirname(__file__), 'entropy.json'),
      substrate=substrate
  )

  ## message call: Alice -> Bob, transfer 100 ENT
  ## generated data: 0xfae3a09d8eaf04151687736326c9fea17e25fc5287613693c912909cb226aa4794f26a4800e1f505000000000000000000000000
  ## Sample transaction in rpc-tes env:
  ##  SELECT * FROM `polkascan`.`data_extrinsic` where module_id = 'Contracts'  and extrinsic_hash='9fb9029d486e5cb684b5386975f55f5b94e2d9b80a341e898cd4238e246369ee';
  scale_data = generate_message_data(substrate, contract, "transfer", args = {
      'to': '5FHneW46xGXgs5mUiveU4sbTyGBzmstUspZC92UhjJM694ty',  # Bob's ss58_address
      'value': 100000000
  })
  # Output: 0xfae3a09d8eaf04151687736326c9fea17e25fc5287613693c912909cb226aa4794f26a4800e1f505000000000000000000000000
  # Note: Bob's public key is 0x8eaf04151687736326c9fea17e25fc5287613693c912909cb226aa4794f26a48
  print("generate_message_data output to_hex: {}".format(scale_data.to_hex()))
  

  alice = Keypair.create_from_uri('//Alice')

  # Query token name/symbol/decimals
  result = contract.read(alice, 'name')
  print('Name:', result.contract_result_data)
  result = contract.read(alice, 'symbol')
  print('Symbol:', result.contract_result_data)
  result = contract.read(alice, 'decimals')
  print('Decimals:', result.contract_result_data)

  # Query total supply
  result = contract.read(alice, 'total_supply')
  # Total supply: 1000000000000000000
  print('Total supply:', result.contract_result_data)

  # Query Alice's balance
  result = contract.read(alice, 'balance_of', args={'owner': alice.public_key})
  # Balance: {'success': {'data': 999900000000, 'flags': 0, 'gas_consumed': 13954500000}}  
  print('Balance:', result.value)
  
  # Query block
  block_hash = "0x17c55e4e5aec752c167cd5ae8f565cef72ece119f5d691408911f6c42f521c14"
  # Retrieve extrinsics in block
  result = substrate.get_runtime_block(block_hash=block_hash)

  for extrinsic in result['block']['extrinsics']:
    if 'account_id' in extrinsic:
      signed_by_address = ss58_encode(address=extrinsic['account_id'], address_type=2)
    else:
      signed_by_address = None
    print('\nModule: {}\nCall: {}\nSigned by: {}'.format(
      extrinsic['call_module'],
      extrinsic['call_function'],
      signed_by_address
    ))

    # Loop through params
    for param in extrinsic['params']:
      if param['type'] == 'LookupSource':
        param['value'] = ss58_encode(address=param['value'], address_type=2)
      if param['type'] == 'Compact<BalanceOf>':
        param['value'] = '{} AQUA'.format(param['value'] / 10**15)
      if param['name'] == 'data' and param['type'] == 'Bytes':
        print("Param 'data' value: {}".format(param['value']))
        param['value'] = decode_message_data(substrate, contract, param['value'])
      print("Param '{}': {}".format(param['name'], param['value']))


if __name__ == '__main__':
  main()
