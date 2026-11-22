# 接口

模块GET使用仓内样例，模块POST可传csv或rows与context，直接计算当前规则。/api/runs使用完整流水线并原子保存。每个阶段返回rows、quarantine、metrics；后续阶段还返回累计隔离。/api/upload接收multipart文件file。/api/runs/<id>/archive只导出一份带清单与证据的CSV。

完整批次负载含closure（关账交接单：closed_at、threshold_seconds、逐文档rows与metrics），由延迟闸门结果按关账口径确定性推导并随批次封存。导出CSV在accepted与quarantine行之后追加一条closure汇总行（关账时刻与统计）和逐文档handover行（reason列为源端/索引端/未归责，evidence含原始时刻与未归责原因），与`/parity`页面读取同一份结论。复核接口只改批次状态，不改写交接行。
