"""Example of a pipeline to demonstrate a simple data science workflow."""
import os
import urllib

import kfp

import kfp_tekton


def data_prep(
    X_train_file: kfp.components.OutputPath(),
    X_test_file: kfp.components.OutputPath(),
    y_train_file: kfp.components.OutputPath(),
    y_test_file: kfp.components.OutputPath(),
):
    import pickle

    import pandas as pd

    from sklearn import datasets
    from sklearn.model_selection import train_test_split

    def get_iris_data() -> pd.DataFrame:
        iris = datasets.load_iris()
        data = pd.DataFrame(
            {
                "sepalLength": iris.data[:, 0],
                "sepalWidth": iris.data[:, 1],
                "petalLength": iris.data[:, 2],
                "petalWidth": iris.data[:, 3],
                "species": iris.target,
            }
        )

        print("Initial Dataset:")
        print(data.head())

        return data

    def create_training_set(dataset: pd.DataFrame, test_size: float = 0.3):
        # Features
        X = dataset[["sepalLength", "sepalWidth", "petalLength", "petalWidth"]]
        # Labels
        y = dataset["species"]

        # Split dataset into training set and test set
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=11
        )

        return X_train, X_test, y_train, y_test

    def save_pickle(object_file, target_object):
        with open(object_file, "wb") as f:
            pickle.dump(target_object, f)

    dataset = get_iris_data()
    X_train, X_test, y_train, y_test = create_training_set(dataset)

    save_pickle(X_train_file, X_train)
    save_pickle(X_test_file, X_test)
    save_pickle(y_train_file, y_train)
    save_pickle(y_test_file, y_test)


def train_model(
    X_train_file: kfp.components.InputPath(),
    y_train_file: kfp.components.InputPath(),
    model_file: kfp.components.OutputPath(),
):
    import pickle

    from sklearn.ensemble import RandomForestClassifier

    def load_pickle(object_file):
        with open(object_file, "rb") as f:
            target_object = pickle.load(f)

        return target_object

    def save_pickle(object_file, target_object):
        with open(object_file, "wb") as f:
            pickle.dump(target_object, f)

    def train_iris(X_train: pd.DataFrame, y_train: pd.DataFrame):
        model = RandomForestClassifier(n_estimators=100)
        model.fit(X_train, y_train)

        return model

    X_train = load_pickle(X_train_file)
    y_train = load_pickle(y_train_file)

    model = train_iris(X_train, y_train)

    save_pickle(model_file, model)


def validate_model(model_file: kfp.components.InputPath()):
    import pickle

    def load_pickle(object_file):
        with open(object_file, "rb") as f:
            target_object = pickle.load(f)

        return target_object

    model = load_pickle(model_file)

    input_values = [[5, 3, 1.6, 0.2]]

    print(f"Performing test prediction on {input_values}")
    result = model.predict(input_values)

    print(f"Response: {result}")


def evaluate_model(
    X_test_file: kfp.components.InputPath(),
    y_test_file: kfp.components.InputPath(),
    model_file: kfp.components.InputPath(),
    mlpipeline_metrics_file: kfp.components.OutputPath("Metrics"),
):
    import json
    import pickle

    from sklearn.metrics import accuracy_score

    def load_pickle(object_file):
        with open(object_file, "rb") as f:
            target_object = pickle.load(f)

        return target_object

    X_test = load_pickle(X_test_file)
    y_test = load_pickle(y_test_file)
    model = load_pickle(model_file)

    y_pred = model.predict(X_test)

    accuracy_score_metric = accuracy_score(y_test, y_pred)
    print(f"Accuracy: {accuracy_score_metric}")

    metrics = {
        "metrics": [
            {
                "name": "accuracy-score",
                "numberValue": accuracy_score_metric,
                "format": "PERCENTAGE",
            },
        ]
    }

    with open(mlpipeline_metrics_file, "w") as f:
        json.dump(metrics, f)


data_prep_op = kfp.components.create_component_from_func(
    data_prep,
    base_image="registry.access.redhat.com/ubi8/python-38",
    packages_to_install=["pandas", "scikit-learn"],
)

train_model_op = kfp.components.create_component_from_func(
    train_model,
    base_image="registry.access.redhat.com/ubi8/python-38",
    packages_to_install=["pandas", "scikit-learn"],
)

evaluate_model_op = kfp.components.create_component_from_func(
    evaluate_model,
    base_image="registry.access.redhat.com/ubi8/python-38",
    packages_to_install=["pandas", "scikit-learn"],
)

validate_model_op = kfp.components.create_component_from_func(
    validate_model,
    base_image="registry.access.redhat.com/ubi8/python-38",
    packages_to_install=["pandas", "scikit-learn"],
)


@kfp.dsl.pipeline(
    name="Iris Pipeline",
)
def iris_pipeline(model_obc: str = "iris-model"):
    data_prep_task = data_prep_op()

    train_model_task = train_model_op(
        data_prep_task.outputs["X_train"],
        data_prep_task.outputs["y_train"],
    )

    evaluate_model_task = evaluate_model_op(  # noqa: F841
        data_prep_task.outputs["X_test"],
        data_prep_task.outputs["y_test"],
        train_model_task.output,
    )

    validate_model_task = validate_model_op(train_model_task.output)  # noqa: F841


if __name__ == "__main__":
    # set the default storage class and mode if they don't already exists
    os.environ["DEFAULT_STORAGE_CLASS"] = os.environ.get(
        "DEFAULT_STORAGE_CLASS", "ocs-storagecluster-ceph-rbd"
    )
    os.environ["DEFAULT_ACCESSMODES"] = os.environ.get(
        "DEFAULT_ACCESSMODES", "ReadWriteOnce"
    )

    kfp_tekton.compiler.TektonCompiler().compile(
        iris_pipeline, __file__.replace(".py", ".yaml")
    )
