---
name: doc-crew-protocol
description: The doc-crew working protocol for shared cloud documents. One pen per team, receipts as the single source of truth, mechanical revert over manual repair, and independent read-back review. Load when coordinating, writing, or reviewing shared-document work as a team.
---

# Doc-Crew Protocol · 每队一支笔

## Why one pen

写入集中在一名成员（scribe）时：回执台账有单一执行者，责任清楚；出错整批机械回退有明确对象；审校的独立性有保障（写的人不核验自己）。

## The loop

1. leader 拆解任务 → 指定文档、区域、验收标准。
2. scribe 先读后写，小步修改，每批写入自动落回执（含改前内容）。
3. reviewer 实读文档逐条核验，报告符合/不符合/无法核验三栏。
4. 不符合 → leader 让 scribe 按回执回退重做；禁止在错误结果上手工修补。
5. leader 汇总：已核验 / 未核验 / 未动手，如实交付。

## Hard rules

- 除 scribe 外任何成员不调用写入类 clouddoc 工具（batch_edit / write_region / reply_comment / apply_for_comment / create_document / workmode 类）。
- 汇报声称"已修改"必须有对应写入回执；对不上账的汇报按未完成处理。
- 回退永远走回执（机械、整批、可拒绝），拒绝时如实上报"该区域已被后续修改"，不做近似恢复。
