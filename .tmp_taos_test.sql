INSERT INTO nengtan.d1 USING nengtan.readings TAGS('nt001','chengzhong','chengzhong','weight') VALUES(now, 0.41) (now-1s, 0.40);
SELECT _wstart, AVG(val) FROM nengtan.readings WHERE box='nt001' AND device='chengzhong' INTERVAL(1s);
