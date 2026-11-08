const labels = {
  name: '名称', title: '游戏名称', enabled: '启用', tags: '标签（空格分隔）', scene_id: '场景', entity_id: '实体', target_id: '追踪目标', template_id: '生成模板', asset_id: '图片',
  width: '宽度', height: '高度', angle: '旋转 °', background: '背景', gravity_x: '重力 X', gravity_y: '重力 Y', color: '颜色', opacity: '不透明度', depth: '显示层级',
  body_type: '刚体类型', shape: '形状', vx: '速度 X', vy: '速度 Y', drag: '阻力', bounce: '弹性', world_bounds: '限制在场景内', solid: '实体碰撞分离',
  initial: '初始值', maximum: '最大生命', value_type: '变量类型', speed: '速度 / 秒', loop: '循环路径', turn_interval_ticks: '转向间隔 / tick',
  interval_ticks: '生成间隔 / tick', ticks: '生命周期 / tick', count: '每次生成数量', max_alive: '存活数量上限', at_tick: '触发 tick',
  left_tag: '左侧标签', right_tag: '右侧标签', phase: '碰撞触发', comparison: '比较', value: '比较 / 设置值', result: '结果', message: '结束提示', target: '作用实体', amount: '数量',
};
export const names = {
  transform: '变换', visual: '外观', body: 'Arcade 刚体', health: '生命', player_control: '玩家控制', seek: '追踪', patrol: '路径巡逻', wander: '随机游走', spawn: '生成实体', lifetime: '生命周期',
  elapsed_tick: '计时触发', overlap: '重叠接触', variable_compare: '变量条件', health_compare: '生命条件', finish: '结束游戏', variable_set: '设置变量', variable_add: '增加变量', damage: '伤害', despawn: '移除实体', scene_change: '切换场景',
};
const enumValues = { body_type: ['dynamic', 'static'], comparison: ['eq', 'ne', 'lt', 'le', 'gt', 'ge'], phase: ['enter', 'stay'], result: ['won', 'lost'], value_type: ['int', 'float', 'bool'] };
export const componentKinds = ['transform', 'visual', 'body', 'health'];
export const behaviorKinds = ['player_control', 'seek', 'patrol', 'wander', 'spawn', 'lifetime'];
export const triggerKinds = ['elapsed_tick', 'overlap', 'variable_compare', 'health_compare'];
export const actionKinds = ['finish', 'variable_set', 'variable_add', 'damage', 'despawn', 'spawn', 'scene_change'];

export function defaultSpec(kind, game, entityId) {
  const entity = entityId ?? game.entities[0]?.id ?? '';
  const variable = game.variables[0];
  const region = { x: 20, y: 20, width: 200, height: 100 };
  const defaults = {
    transform: { x: 100, y: 100, width: 32, height: 32, angle: 0 },
    visual: { shape: 'rect', color: '#f39a42', opacity: 1, depth: 0 },
    body: { body_type: 'dynamic', shape: 'rectangle', vx: 0, vy: 0, drag: 0, bounce: 0, world_bounds: true, solid: false },
    health: { initial: 3, maximum: 3 },
    player_control: { entity_id: entity, speed: 220 },
    seek: { entity_id: entity, target_id: game.entities.find((item) => item.id !== entity)?.id ?? entity, speed: 60 },
    patrol: { entity_id: entity, waypoints: [{ x: 100, y: 100 }, { x: 300, y: 100 }], speed: 80, loop: true },
    wander: { entity_id: entity, speed: 50, turn_interval_ticks: 120 },
    spawn: { template_id: game.entities.find((item) => !item.enabled)?.id ?? entity, count: 1, region },
    lifetime: { entity_id: entity, ticks: 600 },
    elapsed_tick: { at_tick: 3600 }, overlap: { left_tag: 'player', right_tag: 'slime', phase: 'enter' },
    variable_compare: { variable_id: variable?.id ?? '', comparison: 'ge', value: variable?.value_type === 'bool' ? true : 10 },
    health_compare: { entity_id: entity, comparison: 'le', value: 0 },
    finish: { result: 'won', message: '恭喜，挑战完成！' },
    variable_set: { variable_id: variable?.id ?? '', value: variable?.initial ?? 0 },
    variable_add: { variable_id: variable?.id ?? '', amount: 1 },
    damage: { target: 'left', amount: 1 }, despawn: { target: 'right' }, scene_change: { scene_id: game.scenes[0]?.id ?? '' },
  };
  return { kind, ...structuredClone(defaults[kind]) };
}

export function defaultBehavior(kind, game, entityId) {
  return { ...defaultSpec(kind, game, entityId), ...(kind === 'spawn' ? { entity_id: entityId ?? game.entities[0]?.id ?? '', interval_ticks: 180, max_alive: 16 } : {}) };
}

export function createForms(React) {
  const h = React.createElement;
  const button = (text, click, disabled = false) => h('button', { type: 'button', onClick: click, disabled }, text);

  function Fields({ value, onChange, game, prefix = '', omit = [] }) {
    function update(key, next) {
      const changed = { ...value, [key]: next };
      if (key === 'shape' && value.kind === 'visual') {
        if (next === 'asset') changed.asset_id = game.assets[0]?.id ?? '';
        else delete changed.asset_id;
      }
      if (key === 'value_type') changed.initial = next === 'bool' ? false : 0;
      if (key === 'variable_id' && ['variable_compare', 'variable_set'].includes(value.kind)) changed.value = game.variables.find((item) => item.id === next)?.initial ?? 0;
      onChange(changed);
    }
    return h('div', { className: 'game-fields' }, Object.entries(value).filter(([key]) => !['id', 'kind'].includes(key) && !omit.includes(key)).map(([key, item]) => {
      const title = prefix + (labels[key] ?? key.toUpperCase());
      if (key === 'waypoints') return h('fieldset', { key, className: 'game-field-wide' }, h('legend', null, '路径点 · 按顺序移动'), item.map((point, index) => h('div', { key: index, className: 'game-array-row' }, h(Fields, { value: point, game, prefix: `${index + 1} · `, onChange: (next) => update(key, item.map((old, i) => i === index ? next : old)) }), button('移除点', () => update(key, item.filter((_, i) => i !== index)), item.length === 1))), button('添加路径点', () => update(key, [...item, { x: 100, y: 100 }]), item.length >= 64));
      if (item && typeof item === 'object' && !Array.isArray(item)) return h('fieldset', { key, className: 'game-field-wide' }, h('legend', null, key === 'region' ? '生成区域' : title), h(Fields, { value: item, game, prefix: title + ' · ', onChange: (next) => update(key, next) }));
      let options = enumValues[key];
      if (key === 'shape') options = value.kind === 'body' ? ['rectangle', 'circle'] : ['rect', 'ellipse', 'fox', 'slime', 'asset'];
      if (key.endsWith('_id') || key === 'target') {
        const collection = key === 'scene_id' ? game.scenes : key === 'asset_id' ? game.assets : key === 'variable_id' ? game.variables : game.entities;
        options = [...(key === 'target' ? [{ id: 'left', name: '碰撞左侧' }, { id: 'right', name: '碰撞右侧' }] : []), ...collection];
      }
      let control;
      if (options) control = h('select', { value: item, required: true, 'aria-label': title, onChange: (event) => update(key, event.target.value) }, typeof options[0] === 'object' && h('option', { value: '' }, '选择…'), options.map((option) => h('option', { key: option.id ?? option, value: option.id ?? option }, option.name ?? option)));
      else if (typeof item === 'boolean') control = h('input', { type: 'checkbox', checked: item, 'aria-label': title, onChange: (event) => update(key, event.target.checked) });
      else if (key === 'tags') control = h('input', { type: 'text', value: item.join(' '), maxLength: 512, 'aria-label': title, onChange: (event) => update(key, event.target.value.split(/\s+/).filter(Boolean)) });
      else if (typeof item === 'number') control = h('input', { type: 'number', step: ['width', 'height', 'depth', 'at_tick', 'ticks', 'initial', 'maximum', 'count', 'max_alive', 'interval_ticks', 'turn_interval_ticks'].includes(key) && value.value_type !== 'float' ? 1 : 'any', required: true, value: Number.isNaN(item) ? '' : item, 'aria-label': title, onChange: (event) => update(key, event.target.valueAsNumber) });
      else control = h('input', { type: key === 'color' || key === 'background' ? 'color' : 'text', required: true, value: item, maxLength: 120, 'aria-label': title, onChange: (event) => update(key, event.target.value) });
      return h('label', { key, className: typeof item === 'boolean' ? 'game-check' : undefined }, h('span', null, title), control);
    }));
  }

  function Spec({ value, onChange, game, kinds, entityId, behavior = false, fixed = false }) {
    return h('div', { className: 'game-spec' }, h('label', null, h('span', null, '类型'), h('select', { 'aria-label': '类型', value: value.kind, disabled: fixed, onChange: (event) => onChange((behavior ? defaultBehavior : defaultSpec)(event.target.value, game, entityId)) }, kinds.map((kind) => h('option', { key: kind, value: kind }, names[kind])))), h(Fields, { value, onChange, game }));
  }

  function RuleFields({ value, onChange, game, entityId }) {
    return h('div', null,
      h(Fields, { value, game, omit: ['trigger', 'actions'], onChange }),
      h('fieldset', null, h('legend', null, '当 · 触发条件'), h(Spec, { value: value.trigger, game, entityId, kinds: triggerKinds, onChange: (trigger) => onChange({ ...value, trigger }) }), h('p', { className: 'game-help' }, '计时使用场景 tick；变量和生命条件只在 false → true 时触发。60 tick = 1 秒。')),
      value.actions.map((action, index) => h('fieldset', { key: index }, h('legend', null, `则 · 动作 ${index + 1}`), h(Spec, { value: action, game, entityId, kinds: actionKinds, onChange: (next) => onChange({ ...value, actions: value.actions.map((item, i) => i === index ? next : item) }) }), h('div', { className: 'game-button-row' }, button('上移', () => { const actions = [...value.actions]; [actions[index - 1], actions[index]] = [actions[index], actions[index - 1]]; onChange({ ...value, actions }); }, index === 0), button('移除动作', () => onChange({ ...value, actions: value.actions.filter((_, i) => i !== index) }), value.actions.length === 1)))),
      button('添加动作', () => onChange({ ...value, actions: [...value.actions, defaultSpec('finish', game)] }), value.actions.length >= 16),
    );
  }
  return { Fields, Spec, RuleFields };
}
