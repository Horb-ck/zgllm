- /home/zgllm/workspace/elite_server:正式服务器
- /home/zgllm/test_server:测试服务器

常用命令：
- 激活pyhton环境
source /home/zgllm/workspace/elite_server/elite/bin/activate
旧的环境不要再用了，使用新的python环境
source /home/zgllm/workspace/elite_server/new_py/elite11/bin/activate

- 运行python程序
直接 ./run.sh

python ./mcp_server.py
   - -w ：表示工作进程数
   - -b ：访问地址和端口
   - main ：flask启动python文件名
   - app  ：Flask对象名


- ssh复制文件
scp root@180.85.206.21:/home/zgllm/Hck/elite_server .
scp -r openssh-9.9p1.tar.gz root@180.85.206.21:/root
- 查看端口占用
lsof -i:7000
netstat -aon|findstr 7777
- mysql连接
mysql -u root -p
use zgllm;
select * from student where email="20201851@stu.cqu.edu.cn";
delete from student where email="202414131117@stu.cqu.edu.cn";
UPDATE student SET sid = "30169437" WHERE email="roywang@cqu.edu.cn";

1. pip install flask
2. python ./app.py
3. 数据库说明

   数据库——zgllm

   数据表——student

   用户名——root

   密码——123456

   | id   | sid       | password | email     |
   | ---- | --------- | -------- | --------- |
   | 自增 | 学号 唯一 |          | 邮箱 唯一 |

   ```msysql
    CREATE TABLE student (
       id INT AUTO_INCREMENT PRIMARY KEY, 
       sid VARCHAR(50) UNIQUE NOT NULL, 
       email VARCHAR(100) UNIQUE, 
       password VARCHAR(255)
   );
   ```

   
推荐工作流（本地开发 → GitHub → 服务器更新）
1）第一次在本地拉取服务器同款代码（从 GitHub clone）
git clone https://github.com/Horb-ck/zgllm.git
cd <REPO>
git checkout main

2）本地修改、提交、推送到 GitHub
git checkout -b feature/xxx
# 修改代码...
git add .
git commit -m "feat: xxx"
git push -u origin feature/xxx


然后在 GitHub 上发起 PR 合并到 main（或你们小团队也可以直接 push main，但 PR 更稳）。

合并后，本地同步 main：

git checkout main
git pull --rebase

3）服务器更新部署（只拉取 main）

在服务器项目目录：

cd /path/to/elite_server
git checkout main
git pull --ff-only

--ff-only 能强制只做“快进更新”，避免服务器上有本地改动时 git 自动做 merge，把部署环境弄乱。
