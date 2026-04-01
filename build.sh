VERSION=$1
REPO=codenetjp/woodpecker-artifacts-s3-plugin

docker build -t $REPO:$VERSION -t $REPO .
docker push $REPO:$VERSION
docker push $REPO