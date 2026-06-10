import { ArrowUpDown, Code, Download, Filter, RefreshCw, Search, Sparkles } from "lucide-react";
import { StatusTag } from "./StatusTag";

interface TablePreviewPaneProps {
  tableId: string;
  onOpenSqlConsole: () => void;
  onToast: (message: string) => void;
}

export function TablePreviewPane({ tableId, onOpenSqlConsole, onToast }: TablePreviewPaneProps) {
  const isComment = tableId === "comment_infos";
  const isVideo = tableId === "video_infos";

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="hifi-panel-toolbar">
        <div className="hifi-toolbar-left">
          <button className="hifi-toolbar-btn" onClick={() => onToast("数据预览已刷新")}><RefreshCw size={10} /> 刷新</button>
          <button className="hifi-toolbar-btn" onClick={() => onToast("打开过滤器")}><Filter size={10} /> 筛选</button>
          <button className="hifi-toolbar-btn" onClick={() => onToast("打开排序规则")}><ArrowUpDown size={10} /> 排序</button>
          <button className="hifi-toolbar-btn" onClick={() => onToast("已导出数据预览")}><Download size={10} /> 导出</button>
          <button className="hifi-toolbar-btn" onClick={() => onToast("测试数据已生成并写入")}><Sparkles size={10} className="text-yellow-600" /> 生成测试数据</button>
        </div>
        <div className="hifi-toolbar-right">
          <Search size={12} className="text-gray-400 cursor-pointer" />
          <button className="hifi-text-btn flex items-center gap-1" onClick={onOpenSqlConsole}><Code size={11} /> 在 SQL 运行</button>
        </div>
      </div>

      <div className="hifi-table-container flex-1 overflow-auto">
        <table className="hifi-table">
          <thead>
            {isComment ? (
              <tr><th>id</th><th>note_id</th><th>user_id</th><th>content</th><th>status</th><th>created_at</th></tr>
            ) : isVideo ? (
              <tr><th>id</th><th>title</th><th>url</th><th>duration</th><th>play_count</th><th>status</th></tr>
            ) : (
              <tr><th>id</th><th>tenant_id</th><th>name</th><th>account</th><th>status</th><th>created_at</th></tr>
            )}
          </thead>
          <tbody>{isComment ? <CommentRows /> : isVideo ? <VideoRows /> : <UserRows />}</tbody>
        </table>
      </div>

      <div className="hifi-table-footer">
        <span>共 12,345 条</span>
        <div className="hifi-pagination">
          <span className="text-gray-400 cursor-pointer">&lt;</span>
          <span className="hifi-page-num active">1</span>
          <span className="hifi-page-num">2</span>
          <span className="hifi-page-num">3</span>
          <span>...</span>
          <span className="hifi-page-num">1235</span>
          <span className="text-gray-400 cursor-pointer">&gt;</span>
        </div>
        <select className="border border-gray-200 rounded px-1 text-[10px]" defaultValue="10">
          <option value="10">10条/页</option>
          <option value="20">20条/页</option>
        </select>
      </div>
    </div>
  );
}

function UserRows() {
  return <>
    <tr><td>1</td><td>10001</td><td>张三</td><td>zhangsan</td><td><StatusTag value="active" /></td><td>2024-11-16 10:23:45</td></tr>
    <tr><td>2</td><td>10001</td><td>李四</td><td>lisi</td><td><StatusTag value="active" /></td><td>2024-11-16 10:23:45</td></tr>
    <tr><td>3</td><td>10002</td><td>王五</td><td>wangwu</td><td><StatusTag value="inactive" /></td><td>2024-11-16 10:23:45</td></tr>
    <tr><td>4</td><td>10002</td><td>赵六</td><td>zhaoliu</td><td><StatusTag value="active" /></td><td>2024-11-16 10:23:45</td></tr>
  </>;
}

function CommentRows() {
  return <>
    <tr><td>101</td><td>20001</td><td>1</td><td className="max-w-[200px] truncate" title="这个系统界面太漂亮了！">这个系统界面太漂亮了！</td><td><StatusTag value="active" /></td><td>2024-11-17 08:32:00</td></tr>
    <tr><td>102</td><td>20002</td><td>2</td><td className="max-w-[200px] truncate" title="同意！设计细节直接拉满。">同意！设计细节直接拉满。</td><td><StatusTag value="active" /></td><td>2024-11-17 08:45:10</td></tr>
    <tr><td>103</td><td>20001</td><td>3</td><td className="max-w-[200px] truncate" title="数据字典表在哪里配置？">数据字典表在哪里配置？</td><td><StatusTag value="pending" /></td><td>2024-11-17 09:12:05</td></tr>
  </>;
}

function VideoRows() {
  return <>
    <tr><td>501</td><td>智能问数新手引导</td><td>/videos/guide.mp4</td><td>03:45</td><td>1,240</td><td><StatusTag value="active" /></td></tr>
    <tr><td>502</td><td>ER图表关联教程</td><td>/videos/er_tutorial.mp4</td><td>07:20</td><td>890</td><td><StatusTag value="active" /></td></tr>
  </>;
}
