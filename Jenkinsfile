groovy
pipeline {
    agent any

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Check Python') {
            steps {
                bat 'python --version'
                bat 'python -m pip --version'
            }
        }

        stage('Install Dependencies') {
            steps {
                bat 'python -m pip install -r requirements.txt'
                bat 'python -m pip install pytest-html'
            }
        }

        stage('Run Tests and Coverage') {
            steps {
                bat 'python -m pytest -v --html=pytest-report.html --self-contained-html --cov --cov-report=term-missing --cov-report=html:coverage-html'
            }
        }
    }

    post {
        always {
            publishHTML(target: [
                reportDir: '.',
                reportFiles: 'pytest-report.html',
                reportName: 'PlacementPro Test Report',
                keepAll: true,
                alwaysLinkToLastBuild: true,
                allowMissing: true
            ])

            publishHTML(target: [
                reportDir: 'coverage-html',
                reportFiles: 'index.html',
                reportName: 'PlacementPro Coverage Report',
                keepAll: true,
                alwaysLinkToLastBuild: true,
                allowMissing: true
            ])
        }

        success {
            echo 'PlacementPro pipeline completed successfully!'
        }

        failure {
            echo 'PlacementPro pipeline failed. Check the console output.'
        }
    }
}
