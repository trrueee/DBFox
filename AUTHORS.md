# DBFox 作者与正式来源

DBFox 由 GitHub 用户 [@trrueee](https://github.com/trrueee) 发起并维护，规范仓库为：

<https://github.com/trrueee/DBFox>

其他贡献者以该规范仓库的 Git 提交历史和 GitHub Pull Request 记录为准。提交中的显示名称和邮箱只是 Git 元数据；密码学身份以 GitHub 验证的提交或标签签名为准。

DBFox 使用 MIT License。任何人都可以在许可证范围内使用、修改、分发和商业化代码，但分发本软件或其实质性部分时必须保留 [`LICENSE`](LICENSE) 中的版权与许可声明。MIT 授权不代表衍生版本由 DBFox 维护者发布或认可。

## 如何辨认正式版本

只有规范仓库的 [GitHub Releases](https://github.com/trrueee/DBFox/releases) 和由该仓库发布工作流生成的产物属于 DBFox 正式来源。正式 Windows 候选产物同时满足：

1. 构建来源是 `main` 上经 GitHub 验证签名的提交；
2. 安装包具有项目发布证书的有效 Windows Authenticode 签名；
3. 自动更新文件具有 Tauri updater 签名；
4. GitHub 为安装包和更新签名生成可验证的构建来源证明；
5. Release 页面、工作流运行和产物摘要能够关联到同一个 commit SHA。

验证下载文件的构建来源：

```powershell
gh attestation verify .\DBFox_1.0.3_x64_en-US.msi --repo trrueee/DBFox
gh attestation verify .\DBFox_1.0.3_x64-setup.exe --repo trrueee/DBFox
```

本地开发构建、第三方镜像、fork 产物和重新打包文件不属于正式版本，即使其文件名或界面与 DBFox 相同。

## 历史与后续签名

已有公开 Git 历史不做重写，也不为旧提交伪造追溯签名。历史优先权由规范仓库的提交图、GitHub 接收记录、Pull Request 和 Release 记录共同保留。从启用本合同后的维护者提交开始，提交使用 SSH 签名；正式发布工作流拒绝未经 GitHub 验证的源提交。
