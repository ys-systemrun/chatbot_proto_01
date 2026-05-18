docker-compose -p chatbot_invitro up -d --build
docker-compose logs
docker compose -p chatbot_invitro exec app seed
docker compose -p chatbot_invitro exec app debug
docker compose -p chatbot_invitro down
cmd /k