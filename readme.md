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
delete from student where email="20201851@stu.cqu.edu.cn";
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

   
