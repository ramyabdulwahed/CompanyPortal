CREATE TABLE app_user (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin','viewer'))
);

/*one default user to be able to login to the app initially*/
INSERT INTO app_user (username, password_hash, role)
VALUES (
    'admin',
    -- password is: admin123
    'scrypt:32768:8:1$eqiDWt4GehltibPL$c5bbc6f3a3d1f650848296e13ddd00949af03ef8fc587275406b0c4ebea65c61b1100c2159afdd1c9075b3129815214c878a905c972904637e2a007439b0c632',
    'admin'
);

