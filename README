## Aronet

Auto routed and full mesh overlay network based on ipsec and babel. Inspired by https://github.com/NickCao/ranet

### Requirements

Linux:
+ kerner >= 4.8
+ enable vrf module
+ firewall port: 6696(babel), 12025(default for node connectivity)

### Usage

To run aronet, you need two files basically:

#### `config.json`

 `config.json` contains basic configuration for running aronet, example:
 ```json
{
  "private_key": "./test/config/moon/private.pem",
  "organization": "example",
  "common_name": "host-01",
  "daemon": {
    "prefixs": [
      "192.168.128.1/24"
    ]
  },
  "endpoints": [
    {
      "address": "1.1.1.1",
      "port": 12025,
    },
    {
      "address_family": "ip6",
      "address": null,
      "port": 12025,
      "serial_number": 1
    }
  ]
}
```

After aronet started, it will create a vrf device called `aronet` with address in `daemon.prefixs`, then other nodes will route the traffic of `daemon.prefixs` to your node. The `endpoints` tell other nodes how to connect to your node.

#### `registry.json`

`registry.json` contains information of nodes in a mesh overlay network. And your nodes will connect to the nodes in `registry.json`. example:
```json
[
  {
    "public_key": "-- raw pem of public key --",
    "organization": "example",
    "nodes": [
      {
        "common_name": "host-01",
        "endpoints": [
          {
            "address": "2.2.2.2",
            "port": 12345,
          },
          {
            "address": "::1",
            "port": 12345
          }
        ],
        "remarks": {
          "prefixs": [
            "192.168.128.1/24"
          ]
        }
      }
    ]
  },
  {
    "public_key": "-- raw pem of public key --",
    "organization": "example2",
    "nodes": [
      {
        "common_name": "host-01",
        "endpoints": [
          {
            "address": "1.1.1.2",
            "port": 12345
          },
          {
            "address": "::1",
            "port": 12345
          }
        ],
        "remarks": {
          "prefixs": [
            "192.168.129.1/24"
          ]
        }
      }
    ]
  }
]
```

The information of nodes is derived from your `config.json`. As a full example, see configurations under `tests`.

To launch aronet, firstly launch the `daemon`:
```shell
aronet daemon run -c /path/to/config.json
```
And then load the configurations:
```shell
aronet load -c /path/to/config.sjon -r /path/to/registry.json
```
