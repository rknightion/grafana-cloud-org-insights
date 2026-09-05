# Changelog

## [0.3.0](https://github.com/rknightion/grafana-cloud-org-insights/compare/v0.2.1...v0.3.0) (2026-09-05)


### Features

* add lab-validated registry entries and record four live traps ([b899a2c](https://github.com/rknightion/grafana-cloud-org-insights/commit/b899a2c181a4d9149000205a9cdb6f787136b5e7))
* count eBPF zero-code instrumentation and file the coverage-scoring fixes ([215d251](https://github.com/rknightion/grafana-cloud-org-insights/commit/215d251b44149df00f6e840aeeb4af571e480e3b))
* deepen technology classification ([a4e8f55](https://github.com/rknightion/grafana-cloud-org-insights/commit/a4e8f5570bf4e07c8fb0d29b9fa165da10ca2bdb))
* expand the technology registry to 56 validated entries ([33649d5](https://github.com/rknightion/grafana-cloud-org-insights/commit/33649d51bcc754beeef10449f3f34bb5e53860c3))
* file provisioned-but-unused capability as an adoption surface ([75abb5b](https://github.com/rknightion/grafana-cloud-org-insights/commit/75abb5b3d776c5b0db3668e76d886a9edc04cba1))
* grant approved Adaptive Metrics and Traces reads to the per-stack reader ([295dba5](https://github.com/rknightion/grafana-cloud-org-insights/commit/295dba5ef58267c8d78741e5336c29bfd8ca5798))
* publish adjacent datasource estate ([9db6eca](https://github.com/rknightion/grafana-cloud-org-insights/commit/9db6eca677dcd6f5d71794043de56fcf8dfc17bf))
* publish capability adoption opportunities ([f70c927](https://github.com/rknightion/grafana-cloud-org-insights/commit/f70c9273ef4c315d3798784ea84e0d955992eccb))
* show Adaptive Traces reduction and enablement ([b3680c4](https://github.com/rknightion/grafana-cloud-org-insights/commit/b3680c47ddb43b6a5753f56e54f1f1056dcde1cb))


### Bug Fixes

* **auto-rc:** use spaced hyphens, not em dashes ([7e550a8](https://github.com/rknightion/grafana-cloud-org-insights/commit/7e550a85b90d1439035cf7c5b603069f81a2a21c))
* classify coverage service populations without shrinking denominators ([4a03445](https://github.com/rknightion/grafana-cloud-org-insights/commit/4a034458750579a48a7550ea25dac6f964015225))
* drop adaptive-metrics-exemptions:read, the wrong permission mechanism ([b963c80](https://github.com/rknightion/grafana-cloud-org-insights/commit/b963c80c4061ddca2fb83e23ae966657a84f5cb1))
* make coverage scoring denominator defensible ([ab477a0](https://github.com/rknightion/grafana-cloud-org-insights/commit/ab477a0454d673d44f37df2dea98045ac3c6fb5f))
* report technology presence instead of unmatched share ([546aca1](https://github.com/rknightion/grafana-cloud-org-insights/commit/546aca19fc80b23f924dcf349dfd791a0d7b8433))
* stop treating target_info as an OpenTelemetry sentinel ([c511911](https://github.com/rknightion/grafana-cloud-org-insights/commit/c511911814fc1339e7eae8d8cbc5ec64149d33e0))


### Build and CI

* **auto-rc:** trigger on CI completion instead of push ([e523b88](https://github.com/rknightion/grafana-cloud-org-insights/commit/e523b889c3febbe21fdfa5e3e32b47d3cae7b8b1))
* repin the shared reusables to v1.18.1 ([1d030ac](https://github.com/rknightion/grafana-cloud-org-insights/commit/1d030ac34516f74f59e8ee0b47b97e2db269a47e))


### Documentation

* **backlog:** sync fan-out protocol — CodeRabbit review gate ([9234f6a](https://github.com/rknightion/grafana-cloud-org-insights/commit/9234f6a7fcb650f8d03590a0b0aeade64181ead9))
* **backlog:** sync fan-out protocol — success criteria vs write authority ([d629fc2](https://github.com/rknightion/grafana-cloud-org-insights/commit/d629fc2e49777aeec928dcf4917f6a7fb84bf42f))
* complete Pillar K validation ([2784cbb](https://github.com/rknightion/grafana-cloud-org-insights/commit/2784cbb57c3b856f521e21066a40c9c5080e41b4))
* re-import the fan-out protocol at c1e6cb0 ([a998016](https://github.com/rknightion/grafana-cloud-org-insights/commit/a998016594f9d8019ee6d7bd6773ea1871908550))
* settle instrumentation evidence semantics ([502cc43](https://github.com/rknightion/grafana-cloud-org-insights/commit/502cc438f70ba7b11f18553fdb65d760d4d4a08b))
* sync agent-docs, a wave's launch message is a file not a chat block ([6233675](https://github.com/rknightion/grafana-cloud-org-insights/commit/6233675aee8381edace65903cc387d6b21183de0))
* sync Astra routing and default wave reports to files ([3401b95](https://github.com/rknightion/grafana-cloud-org-insights/commit/3401b95c6a4cbf560a655d303756cc31999037e9))
* sync optional Astra fan-out routing and run contracts ([b9c332a](https://github.com/rknightion/grafana-cloud-org-insights/commit/b9c332a49a94ff2f118d5356977d12d041ea9fcd))


### Miscellaneous

* align CodeRabbit review configuration ([556d718](https://github.com/rknightion/grafana-cloud-org-insights/commit/556d718da79e2e6682a82ec7efdda975f0b4df58))
* **backlog:** add GCI-0021 — migrate the repo task surface to just ([cdf7404](https://github.com/rknightion/grafana-cloud-org-insights/commit/cdf74045c0ce73264bf709182620ea5bd0cae9b2))
* **backlog:** ratify ci as the sanctioned superset of check ([fe14d2d](https://github.com/rknightion/grafana-cloud-org-insights/commit/fe14d2d99fd71d56bdb5d648ff0b5cbc18d3a515))
* **backlog:** wire the fleet migration ordering into this task ([4bdaf92](https://github.com/rknightion/grafana-cloud-org-insights/commit/4bdaf926e0486f41b308eca8c726fbda8127595c))
* **deps:** update opentofu/setup-opentofu action to v2 ([#9](https://github.com/rknightion/grafana-cloud-org-insights/issues/9)) ([9a6f337](https://github.com/rknightion/grafana-cloud-org-insights/commit/9a6f337af19a06af54a246ad43e9ff6c3da1fe2a))
* **deps:** update python docker tag to v3.14 ([#13](https://github.com/rknightion/grafana-cloud-org-insights/issues/13)) ([439f420](https://github.com/rknightion/grafana-cloud-org-insights/commit/439f4207f381418ae3a5fcd04e58805bb9fc7109))
* **deps:** update python:3.14-slim docker digest to 656d12e ([#22](https://github.com/rknightion/grafana-cloud-org-insights/issues/22)) ([d6d1464](https://github.com/rknightion/grafana-cloud-org-insights/commit/d6d14644789c7c22ebd521dfe27140ac91c0940e))
* **deps:** update python:3.14-slim docker digest to cad9a2c ([#24](https://github.com/rknightion/grafana-cloud-org-insights/issues/24)) ([588a886](https://github.com/rknightion/grafana-cloud-org-insights/commit/588a8862b6485a1086b9ad9b84b12c063d1b6c01))
* **deps:** update python:3.14-slim docker digest to cae66f2 ([#14](https://github.com/rknightion/grafana-cloud-org-insights/issues/14)) ([060f520](https://github.com/rknightion/grafana-cloud-org-insights/commit/060f520e76b0f397af72cea32965467096322c59))
* **deps:** update rknightion/.github action to v1.11.0 ([#17](https://github.com/rknightion/grafana-cloud-org-insights/issues/17)) ([9192194](https://github.com/rknightion/grafana-cloud-org-insights/commit/919219478a36f62981de2e566097b92d64418ccc))
* **deps:** update rknightion/.github action to v1.14.0 ([#18](https://github.com/rknightion/grafana-cloud-org-insights/issues/18)) ([50846da](https://github.com/rknightion/grafana-cloud-org-insights/commit/50846da28f8e194d7e716c0d542a3ce2a057b45c))
* **deps:** update rknightion/.github action to v1.15.1 ([#19](https://github.com/rknightion/grafana-cloud-org-insights/issues/19)) ([cf9328d](https://github.com/rknightion/grafana-cloud-org-insights/commit/cf9328d36f7d721432109893cb074213eb9c7a8b))
* **deps:** update rknightion/.github action to v1.17.0 ([#20](https://github.com/rknightion/grafana-cloud-org-insights/issues/20)) ([69ffa99](https://github.com/rknightion/grafana-cloud-org-insights/commit/69ffa99d297153682341c7969f49875953134cfe))
* **deps:** update rknightion/.github action to v1.17.1 ([#21](https://github.com/rknightion/grafana-cloud-org-insights/issues/21)) ([d74b1aa](https://github.com/rknightion/grafana-cloud-org-insights/commit/d74b1aa0438ab076d2bdd6fc1bab45fe6ba90aa7))
* **deps:** update rknightion/.github action to v1.18.0 ([#23](https://github.com/rknightion/grafana-cloud-org-insights/issues/23)) ([d4cac65](https://github.com/rknightion/grafana-cloud-org-insights/commit/d4cac65cd1fdf9a5cca609c0ffb47b0f999c8921))
* **deps:** update rknightion/.github action to v1.20.0 ([#25](https://github.com/rknightion/grafana-cloud-org-insights/issues/25)) ([18687b4](https://github.com/rknightion/grafana-cloud-org-insights/commit/18687b413832a34f62523d522c41a1b774dec553))
* **deps:** update rknightion/.github action to v1.9.8 ([#15](https://github.com/rknightion/grafana-cloud-org-insights/issues/15)) ([ceb9da0](https://github.com/rknightion/grafana-cloud-org-insights/commit/ceb9da08a7b5012bb3f0dc19cd9d0aba64ea298c))
* **deps:** update rknightion/.github action to v1.9.9 ([#16](https://github.com/rknightion/grafana-cloud-org-insights/issues/16)) ([60ed2ab](https://github.com/rknightion/grafana-cloud-org-insights/commit/60ed2ab8f7b2cba8d5597a9fbadde6ea01c9e93e))
* finalize GCI-0021 ([a912097](https://github.com/rknightion/grafana-cloud-org-insights/commit/a9120979c44bed60b678479976c468751138011e))
* migrate task surface to just ([a28e9fa](https://github.com/rknightion/grafana-cloud-org-insights/commit/a28e9fa1449465282bca66d94f5779cca49717ca))
* park adaptive traces route discovery ([3b88c2e](https://github.com/rknightion/grafana-cloud-org-insights/commit/3b88c2ec899fa1860b3988aae6d42abca18a05a8))
* record the integration-dashboard decision and verify the unscoring figures ([c044d17](https://github.com/rknightion/grafana-cloud-org-insights/commit/c044d1764dc3345b62661d6f8f20fe226ec293fa))
* settle the two service-register classification decisions ([9efd736](https://github.com/rknightion/grafana-cloud-org-insights/commit/9efd736c4173f83c41a67a58d4048ec16aefaf36))
* track the Pillar K review findings as backlog items ([f8bdecc](https://github.com/rknightion/grafana-cloud-org-insights/commit/f8bdecc5f350f34c35c0aae8f6d4d3025d175f6d))

## [0.2.1](https://github.com/rknightion/grafana-cloud-org-insights/compare/v0.2.0...v0.2.1) (2026-08-25)


### Bug Fixes

* preserve empty Pyroscope measurements ([1ecd814](https://github.com/rknightion/grafana-cloud-org-insights/commit/1ecd8146610695610c771b43c39c2ce77256866b))


### Miscellaneous

* Configure Renovate ([a7c036f](https://github.com/rknightion/grafana-cloud-org-insights/commit/a7c036fe62fbe24d38ad3df37b7f8666dd64a902))
* **deps:** update actions/setup-python action to v7 ([#8](https://github.com/rknightion/grafana-cloud-org-insights/issues/8)) ([e48db3b](https://github.com/rknightion/grafana-cloud-org-insights/commit/e48db3bc5d2f2685abc1ac48d942207cd9c220f9))
* **deps:** update dependency python to 3.14 ([#7](https://github.com/rknightion/grafana-cloud-org-insights/issues/7)) ([e0f113d](https://github.com/rknightion/grafana-cloud-org-insights/commit/e0f113d79acaaf4c2f33be59487a8ff12f3b897d))
* **deps:** update opentofu/setup-opentofu action to v1.0.8 ([#5](https://github.com/rknightion/grafana-cloud-org-insights/issues/5)) ([1b283d6](https://github.com/rknightion/grafana-cloud-org-insights/commit/1b283d6d44e9027a3fecff56831e5f8471b28abf))

## [0.2.0](https://github.com/rknightion/grafana-cloud-org-insights/compare/v0.1.0...v0.2.0) (2026-08-25)


### Features

* add observed estate coverage dashboard ([cceb356](https://github.com/rknightion/grafana-cloud-org-insights/commit/cceb35616673407b448ccdbd7a07e0bbce4d7037))
* add observed estate coverage pillar ([efccdd1](https://github.com/rknightion/grafana-cloud-org-insights/commit/efccdd160a98da041a7e917d190a7052285fa4b8))
* add observed footprint panels ([a9821b0](https://github.com/rknightion/grafana-cloud-org-insights/commit/a9821b0d498dc730c70cd3fbce0ad94bbf13ec01))
* add technology asset registry ([4b19257](https://github.com/rknightion/grafana-cloud-org-insights/commit/4b192577e016fd79760f35a579d4fdd28d126b57))
* complete Pillar K value capture ([f94a5cb](https://github.com/rknightion/grafana-cloud-org-insights/commit/f94a5cbdca3c4cc5bda6017adcd6ae4c174a313e))
* inventory observed signal labels ([63ff625](https://github.com/rknightion/grafana-cloud-org-insights/commit/63ff625365d2549ec724cc92c80d9a43b1beb372))


### Build and CI

* bump the broker-token action pin ([4a0786c](https://github.com/rknightion/grafana-cloud-org-insights/commit/4a0786c89a6acae8619acd00b952f66aad641e74))


### Documentation

* make the runbook a procedure a new deployment can be built from ([11b6b47](https://github.com/rknightion/grafana-cloud-org-insights/commit/11b6b4782786eb75a1356243ec24d198e6afbd81))
* publish the docs site to the m7kni.io hub ([3f38b9a](https://github.com/rknightion/grafana-cloud-org-insights/commit/3f38b9a42cf9dc0d4c43b33bcdd05c25255f3b37))
* record v0.1.0 publication evidence ([b69b180](https://github.com/rknightion/grafana-cloud-org-insights/commit/b69b1801f10240a02bd52dff70463ae619762746))
* use the spaced hyphen, not the em dash ([28a3e18](https://github.com/rknightion/grafana-cloud-org-insights/commit/28a3e18383397119e1aedaf8ef78216bfa4f7eda))


### Miscellaneous

* close completed Pillar K tasks ([30e47fc](https://github.com/rknightion/grafana-cloud-org-insights/commit/30e47fcb80abe646593c3f9b72902f4c234c1913))

## 0.1.0 (2026-08-24)


### Documentation

* record clean repository recreation ([ab93044](https://github.com/rknightion/grafana-cloud-org-insights/commit/ab93044062cbda0f5b8141d2cd2391440c943682))
* record GitHub history purge blocker ([f64d073](https://github.com/rknightion/grafana-cloud-org-insights/commit/f64d073aa70d572320d38a2a1e03fcf08441c5ae))
