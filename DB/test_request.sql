SELECT prk.private_key_sign, prk.public_key_sign, prk.private_key_encrypt, prk.public_key_encrypt
        FROM Emails em
        LEFT JOIN PersonalRSAKeys prk ON em.id = prk.email_id
        WHERE em.email = 'modex.modex@mail.ru' AND prk.create_date <= '2024-11-24 23:24:44'
        ORDER BY prk.create_date DESC
        LIMIT 1