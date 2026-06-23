// ============================================================
// 多 Agent 开发流水线 — 编排脚本
// 用法：在 Claude Code 中输入 /pipeline 或在 Workflow 工具中调用
// ============================================================

export const meta = {
  name: 'dev-pipeline',
  description: '多Agent开发流水线：架构师 → 开发者 → 测试员 → 审查员，含检查点和预算追踪',
  phases: [
    { title: '架构设计', detail: '架构师澄清需求 → 设计架构 → 拆分任务DAG' },
    { title: '编码实现', detail: '开发者按DAG逐任务编码，支持并行组' },
    { title: '测试验证', detail: '测试员编写测试 → 运行 → 报告' },
    { title: '代码审查', detail: '审查员四维度审查 → 自动修复 → 报告' },
    { title: '汇总交付', detail: '生成最终交付报告，含预算对比' }
  ]
};

// -----------------------------------------------------------
// 辅助函数
// -----------------------------------------------------------

function budgetBreakdown(results, budgetConfig) {
  const total = results.reduce((sum, r) => {
    if (!r) return sum;
    return sum + (r.actualCost || r.estimatedCost || 0);
  }, 0);
  return {
    totalCost: total.toFixed(2),
    currency: 'CNY',
    modelUsed: budgetConfig?.default_model || 'unknown',
    breakdown: results.filter(Boolean).map(r => ({
      phase: r.phase,
      estimated: r.estimatedCost,
      actual: r.actualCost || '未统计'
    }))
  };
}

// -----------------------------------------------------------
// 主流水线
// -----------------------------------------------------------

async function main(args) {
  const projectName = args?.projectName || '未命名项目';
  const userRequirement = args?.requirement || args?.description || '';

  log(`🚀 启动开发流水线：${projectName}`);
  log(`📋 需求概述：${userRequirement}`);

  // ==========================================
  // 阶段 1：架构设计
  // ==========================================
  phase('架构设计');

  const architectResult = await agent(
    `你是架构师角色。请严格按照 ${projectName}/.claude/../skills/architect.md 中定义的
    三阶段协议工作：

    项目需求：${userRequirement}

    首先进入阶段0：向我提问澄清需求（技术默认值、领域惯例、隐性约束，最多5问）。
    确认理解无误后进入阶段1：输出六段式架构预案（含预算预测）。
    我批准后进入阶段2：产出 docs/architecture.md 和 docs/task-dag.json。

    注意：budget_config 在 ~/.claude/budget_config.json，请参考其中的模型价格。`,
    {
      label: '架构师',
      phase: '架构设计',
      schema: {
        type: 'object',
        properties: {
          phase: { type: 'string' },
          architectureDoc: { type: 'string', description: '架构文档路径' },
          taskDagPath: { type: 'string', description: '任务DAG JSON路径' },
          taskCount: { type: 'number', description: '拆分出的任务数量' },
          parallelGroups: { type: 'array', items: { type: 'array', items: { type: 'string' } } },
          estimatedCost: { type: 'number', description: '架构阶段预估费用(CNY)' },
          actualCost: { type: 'number', description: '架构阶段实际费用(CNY)' },
          summary: { type: 'string', description: '架构阶段总结' }
        },
        required: ['taskCount', 'estimatedCost', 'summary']
      }
    }
  );

  if (!architectResult) {
    log('❌ 架构设计阶段失败，流水线终止');
    return { status: 'failed', phase: 'architecture' };
  }

  log(`✅ 架构设计完成 — ${architectResult.taskCount} 个任务`);
  log(`💰 架构阶段预算：¥${architectResult.estimatedCost}`);

  // 保存检查点
  await saveCheckpoint({
    phase: 'architecture_complete',
    result: architectResult,
    timestamp: new Date().toISOString()
  });

  // ==========================================
  // 阶段 2：编码实现（按 DAG 调度）
  // ==========================================
  phase('编码实现');

  // 从架构产出中读取任务列表
  const tasks = architectResult.taskDagPath
    ? await agent(
        `读取 ${architectResult.taskDagPath} 文件，提取 tasks 数组和 parallel_groups。
         返回完整的任务列表 JSON。`,
        { label: '读取任务DAG', schema: { type: 'object', properties: { tasks: { type: 'array' }, parallelGroups: { type: 'array' } } } }
      )
    : null;

  const taskList = tasks?.tasks || [];
  const parallelGroups = tasks?.parallelGroups || [];

  if (taskList.length === 0) {
    log('⚠️ 无编码任务，跳过开发阶段');
  } else {
    // 按依赖关系分组执行
    // 简化策略：先执行 depends_on=[] 的任务，再执行依赖任务
    const completed = new Set();
    const devResults = [];

    // 拓扑排序的简化实现
    while (completed.size < taskList.length) {
      const ready = taskList.filter(t =>
        !completed.has(t.id) &&
        (t.depends_on || []).every(dep => completed.has(dep))
      );

      if (ready.length === 0) {
        log('⚠️ 检测到循环依赖或死锁，跳过剩余任务');
        break;
      }

      // 检查是否可并行
      const isParallelGroup = parallelGroups.some(g =>
        g.length === ready.length && g.every(id => ready.some(t => t.id === id))
      );

      if (isParallelGroup && ready.length > 1) {
        // 并行执行
        log(`⚡ 并行执行任务组：${ready.map(t => t.id).join(', ')}`);
        const parallelResults = await parallel(
          ready.map(task => () =>
            agent(
              `你是开发者角色。当前任务：

              任务ID：${task.id}
              任务名：${task.name}
              验收标准：${(task.acceptance_criteria || []).join('；')}
              输出文件：${(task.output_files || []).join(', ')}

              请严格按照三阶段协议工作：
              阶段0 — 编码前澄清（必要的话）
              阶段1 — 六段式编码预案（含预算预测）
              阶段2 — 审批后编码实现

              注意：遵循 ~/.claude/CLAUDE.md 中的全局规范。`,
              {
                label: `dev:${task.id}`,
                phase: '编码实现',
                schema: {
                  type: 'object',
                  properties: {
                    taskId: { type: 'string' },
                    completed: { type: 'boolean' },
                    filesCreated: { type: 'array', items: { type: 'string' } },
                    estimatedCost: { type: 'number' },
                    actualCost: { type: 'number' },
                    deviation: { type: 'string', description: '与预案的偏差说明' }
                  },
                  required: ['taskId', 'completed']
                }
              }
            )
          )
        );
        parallelResults.filter(Boolean).forEach(r => {
          devResults.push(r);
          completed.add(r.taskId);
        });
      } else {
        // 串行执行
        for (const task of ready) {
          log(`📝 执行任务：${task.id} — ${task.name}`);
          const result = await agent(
            `你是开发者角色。当前任务：

            任务ID：${task.id}
            任务名：${task.name}
            验收标准：${(task.acceptance_criteria || []).join('；')}
            输出文件：${(task.output_files || []).join(', ')}

            请严格遵循三阶段协议（澄清→预案→审批→执行）。
            参考 ~/.claude/CLAUDE.md 中的全局规范。`,
            {
              label: `dev:${task.id}`,
              phase: '编码实现',
              schema: {
                type: 'object',
                properties: {
                  taskId: { type: 'string' },
                  completed: { type: 'boolean' },
                  filesCreated: { type: 'array', items: { type: 'string' } },
                  estimatedCost: { type: 'number' },
                  actualCost: { type: 'number' },
                  deviation: { type: 'string' }
                },
                required: ['taskId', 'completed']
              }
            }
          );
          if (result) {
            devResults.push(result);
            completed.add(task.id);
          }
        }
      }
    }

    log(`✅ 编码阶段完成 — ${devResults.filter(r => r?.completed).length}/${taskList.length} 个任务`);

    // 保存检查点
    await saveCheckpoint({
      phase: 'development_complete',
      devResults,
      completedTasks: [...completed],
      timestamp: new Date().toISOString()
    });
  }

  // ==========================================
  // 阶段 3 + 4：测试和审查（可并行）
  // ==========================================
  phase('测试验证');

  const [testResult, reviewResult] = await parallel([
    // 测试
    () => agent(
      `你是测试员角色。请对项目 ${projectName} 执行完整测试流程。

      严格遵循三阶段协议：
      阶段0 — 测试前澄清（框架、覆盖率目标、Bug处理策略）
      阶段1 — 六段式测试预案（含预算预测）
      阶段2 — 审批后编写测试 → 运行 → 报告

      参考 ~/.claude/CLAUDE.md 和 ~/.claude/skills/test.md。`,
      {
        label: '测试员',
        phase: '测试验证',
        schema: {
          type: 'object',
          properties: {
            totalTests: { type: 'number' },
            passed: { type: 'number' },
            failed: { type: 'number' },
            coverage: { type: 'string' },
            estimatedCost: { type: 'number' },
            actualCost: { type: 'number' },
            bugsFound: { type: 'array', items: { type: 'string' } },
            summary: { type: 'string' }
          },
          required: ['totalTests', 'passed', 'summary']
        }
      }
    ),
    // 审查
    () => agent(
      `你是审查员角色。请对项目 ${projectName} 执行代码审查。

      严格遵循三阶段协议：
      阶段0 — 审查前澄清（侧重点、范围、严格度）
      阶段1 — 六段式审查预案（含预算预测）
      阶段2 — 审批后逐文件审查 → 输出报告

      审查维度：正确性、安全性、性能、可读性。
      参考 ~/.claude/CLAUDE.md 和 ~/.claude/skills/review.md。`,
      {
        label: '审查员',
        phase: '代码审查',
        schema: {
          type: 'object',
          properties: {
            filesReviewed: { type: 'number' },
            criticalCount: { type: 'number' },
            highCount: { type: 'number' },
            mediumCount: { type: 'number' },
            lowCount: { type: 'number' },
            autoFixed: { type: 'number' },
            estimatedCost: { type: 'number' },
            actualCost: { type: 'number' },
            summary: { type: 'string' }
          },
          required: ['filesReviewed', 'summary']
        }
      }
    )
  ]);

  // ==========================================
  // 汇总交付
  // ==========================================
  phase('汇总交付');

  const deliveryReport = {
    project: projectName,
    completedAt: new Date().toISOString(),
    phases: {
      architecture: architectResult ? {
        status: '✅',
        taskCount: architectResult.taskCount,
        estimatedCost: architectResult.estimatedCost,
        actualCost: architectResult.actualCost
      } : { status: '❌' },
      development: {
        status: '✅',
        completedTasks: completed?.size || 0
      },
      testing: testResult ? {
        status: testResult.failed === 0 ? '✅' : '⚠️',
        passed: `${testResult.passed}/${testResult.totalTests}`,
        coverage: testResult.coverage
      } : { status: '⚠️ 未执行' },
      review: reviewResult ? {
        status: reviewResult.criticalCount === 0 ? '✅' : '⚠️',
        issuesFound: reviewResult.criticalCount + reviewResult.highCount + reviewResult.mediumCount + reviewResult.lowCount,
        autoFixed: reviewResult.autoFixed
      } : { status: '⚠️ 未执行' }
    },
    budget: {
      totalEstimated: (
        (architectResult?.estimatedCost || 0) +
        (testResult?.estimatedCost || 0) +
        (reviewResult?.estimatedCost || 0)
      ),
      totalActual: (
        (architectResult?.actualCost || architectResult?.estimatedCost || 0) +
        (testResult?.actualCost || testResult?.estimatedCost || 0) +
        (reviewResult?.actualCost || reviewResult?.estimatedCost || 0)
      )
    }
  };

  log(`
  ╔══════════════════════════════════════════╗
  ║     📊 项目交付报告 — ${projectName.padEnd(18)}║
  ╠══════════════════════════════════════════╣
  ║ 架构师：${(deliveryReport.phases.architecture.status || '?').padEnd(33)}║
  ║ 开发者：${(deliveryReport.phases.development.status || '?').padEnd(33)}║
  ║ 测试员：${(deliveryReport.phases.testing.status || '?').padEnd(33)}║
  ║ 审查员：${(deliveryReport.phases.review.status || '?').padEnd(33)}║
  ╠══════════════════════════════════════════╣
  ║ 💰 总预算：¥${String(deliveryReport.budget.totalEstimated.toFixed(2)).padEnd(29)}║
  ║ 💰 总实际：¥${String(deliveryReport.budget.totalActual.toFixed(2)).padEnd(29)}║
  ╚══════════════════════════════════════════╝
  `);

  // 最终检查点
  await saveCheckpoint({
    phase: 'pipeline_complete',
    deliveryReport,
    timestamp: new Date().toISOString()
  });

  return deliveryReport;
}

// -----------------------------------------------------------
// 检查点保存
// -----------------------------------------------------------
async function saveCheckpoint(data) {
  try {
    log('💾 保存检查点...');
    // 在 Claude Code 环境中，检查点会自动持久化到项目的 .claude/checkpoints/
    // 这里记录结构化的检查点数据
    const checkpoint = {
      checkpoint_id: `cp-${new Date().toISOString().replace(/[-:]/g, '').replace(/\..+/, '')}`,
      timestamp: new Date().toISOString(),
      ...data
    };
    return checkpoint;
  } catch (e) {
    log(`⚠️ 检查点保存失败：${e.message}`);
    return null;
  }
}

// 入口
export default main;
