/** The example uses the same typed increment operations available to users. */
export function survivalOperations(sceneId) {
  const scene = { id: sceneId };
  const ref = (name) => ({ ref: name });
  return [
    { kind: 'scene_modify', scene_id: scene, scene: { name: '森林 · 生存 60 秒', width: 800, height: 600, background: '#152d2c', gravity_x: 0, gravity_y: 0 } },
    { kind: 'entity_create', entities: [
      { scene_id: scene, name: '狐狸', ref: 'fox', tags: ['player'], components: [{ kind: 'transform', x: 400, y: 300, width: 36, height: 36 }, { kind: 'visual', shape: 'fox', color: '#f39a42', depth: 10 }, { kind: 'body', shape: 'circle' }, { kind: 'health', initial: 3, maximum: 3 }] },
      { scene_id: scene, name: '史莱姆模板', ref: 'slime', enabled: false, tags: ['slime'], components: [{ kind: 'transform', x: 40, y: 40, width: 28, height: 28 }, { kind: 'visual', shape: 'slime', color: '#78c791' }, { kind: 'body', shape: 'circle' }] },
      { scene_id: scene, name: '林地入口', ref: 'spawner', components: [{ kind: 'transform', x: 400, y: 26, width: 20, height: 20 }] },
    ] },
    { kind: 'behavior_create', behavior: { kind: 'player_control', entity_id: ref('fox'), speed: 230 } },
    { kind: 'behavior_create', behavior: { kind: 'seek', entity_id: ref('slime'), target_id: ref('fox'), speed: 58 } },
    { kind: 'behavior_create', behavior: { kind: 'lifetime', entity_id: ref('slime'), ticks: 1500 } },
    { kind: 'behavior_create', behavior: { kind: 'spawn', entity_id: ref('spawner'), template_id: ref('slime'), interval_ticks: 150, count: 1, max_alive: 24, region: { x: 30, y: 25, width: 740, height: 20 } } },
    { kind: 'variable_create', variable: { name: 'encounters', value_type: 'int', initial: 0 }, ref: 'encounters' },
    { kind: 'rule_create', rule: { scene_id: scene, name: '碰到史莱姆扣血', trigger: { kind: 'overlap', left_tag: 'player', right_tag: 'slime', phase: 'enter' }, actions: [{ kind: 'damage', target: 'left', amount: 1 }, { kind: 'variable_add', variable_id: ref('encounters'), amount: 1 }, { kind: 'despawn', target: 'right' }] } },
    { kind: 'rule_create', rule: { scene_id: scene, name: '生命归零', trigger: { kind: 'health_compare', entity_id: ref('fox'), comparison: 'le', value: 0 }, actions: [{ kind: 'finish', result: 'lost', message: '狐狸被追上了。调整路线再试一次。' }] } },
    { kind: 'rule_create', rule: { scene_id: scene, name: '存活 60 秒', trigger: { kind: 'elapsed_tick', at_tick: 3600 }, actions: [{ kind: 'finish', result: 'won', message: '狐狸成功守住了森林！' }] } },
  ];
}
