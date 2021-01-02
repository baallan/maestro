# Maestro
LDMS Monitoring Cluster Load Balancing Service

Maestro is a Python3 implementation of a service that load balances
a cluster configuration across a number of configured Aggregators.

Aggregators are configured in groups, and groups are organized into a
hierarchy. The lowest level of the hierarchy (level 1) communicate
with the sampler daemons; 2nd level aggregators monitor 1st level
aggregators, 3rd level aggregators monitor 2nd level aggregators
and so on.

There are multiple goals of the __maestro__ daemon:
* Simplify the monitoring configuration of a large cluster
* Create a more resilient and responsive monitoring infrastructure
* Monitor the health and performance of aggregators in the cluster
* Manage aggregator failure by rebalancing the distributed
configuration across the remaining aggregators in a group

In this current release, Maestro does not start and start __ldmsd__
daemons, however, this feature is planned for the future.

## Configuration Management

A cluster's configuration is mangaged in a distributed RAFT based
key-value store called __etcd__. The __etcd__ service is queried using
the python _etcd3_ client interface.

There are two configuration files consumed by __maestro__:
1. A file that defines the _etcd_ cluster configuration
2. A file that defines the LDMS Cluster Configuration

### ETCD Cluster Configuration

Maestro consumes configuration files in YAML format.

Here's an example of an _etcd_ cluster configuration:

```yaml
cluster: voltrino
members:
  - host: 10.128.0.7
    port: 2379
members:
  - host: 10.128.0.8
    port: 2379
members:
  - host: 10.128.0.9
    port: 2379
```

And here is an example of a LDMS Cluster Configuration File:

```yaml
hosts:
  - names : &sampler-hosts "nid[00012-00200]"
    hosts : "nid[00012-00200]"
    ports : "10001"
    xprt : sock
    auth :
      name  : munge
      config  :
          domain : samplers

  - names : &l1-agg-hosts "agg-[11-14]"
    hosts : "nid00002"
    ports : "[30011-30014]"
    xprt : sock
    auth :
      name  : munge
      config  :
        domain : aggregators

  - names : &l2-agg-hosts "agg-[21,22]"
    hosts : "nid00003"
    ports : "[30021,30022]"
    xprt : sock
    auth :
      name  : munge
      config  :
        domain : aggregators

  - names : &l3-agg-hosts "agg-31"
    hosts : "nid00004"
    ports : "30031"
    xprt : sock
    auth :
      name  : munge
      config  :
        domain : users

aggregators:
  - names : *l1-agg-hosts
    hosts : *l1-agg-hosts
    group : l1-agg

  - names : *l2-agg-hosts
    hosts : *l2-agg-hosts
    group: l2-agg

  - names : agg-31
    hosts : "agg-31"
    group : l3-agg

producers:
# This informs the L1 load balance group what is being distributed across
# the L1 aggregator nodes
  - names     : *sampler-hosts
    hosts     : *sampler-hosts
    group     : l1-agg
    reconnect : 20s
    type      : active
    updaters  :
      - l1-all

# This informs the L2 load balance group what is being distributed across
# the L2 aggregator nodes
  - names      : *l1-agg-hosts
    hosts      : *l1-agg-hosts
    group      : l2-agg
    reconnect  : 20s
    type       : active
    updaters   :
      - l2-all

# This informs the L3 load balance group what is being distributed across
# the L3 aggregator node
  - names      : *l2-agg-hosts    # is this really needed?
    hosts      : *l2-agg-hosts
    group      : l3-agg
    reconnect  : 20s
    type       : active
    updaters  :
      - l3-all


updaters:
- name  : all           # must be unique within group
  group : l1-agg
  interval : "1.0s:0ms"
  sets :
    - regex : .*        # regular expression matching set name or schema
      field : inst      # 'instance' or 'schema'
  producers :
    - regex : .*        # regular expression matching producer name
                        # this is evaluated on the Aggregator, not
                        # at configuration time'
- name  : all
  group : l2-agg
  interval : "1.0s:250ms"
  sets :
    - regex : .*
      field : inst
  producers :
    - regex : .*

- name  : all
  group : l3-agg
  interval : "1.0s:500ms"
  sets :
    - regex : .*
      field : inst
  producers :
    - regex : .*

```

