CREATE DATABASE IF NOT EXISTS databox_ssl;

CREATE TABLE IF NOT EXISTS databox_ssl.orders (
  id INT PRIMARY KEY AUTO_INCREMENT,
  channel VARCHAR(50),
  amount DECIMAL(10,2),
  created_at DATETIME
);

INSERT INTO databox_ssl.orders (channel, amount, created_at) VALUES
('xhs', 99.90, NOW()),
('douyin', 199.00, NOW()),
('wechat', 59.50, NOW());

CREATE USER IF NOT EXISTS 'databox_readonly'@'%' IDENTIFIED BY 'readonly_pass';

GRANT SELECT ON databox_ssl.* TO 'databox_readonly'@'%';

ALTER USER 'databox_readonly'@'%' REQUIRE SSL;

FLUSH PRIVILEGES;
