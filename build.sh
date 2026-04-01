VERSION=$1
REPO=ghcr.io/otani-sg/woodpecker-artifacts-s3-plugin

docker build -t $REPO:$VERSION -t $REPO .
docker push $REPO:$VERSION
docker push $REPO